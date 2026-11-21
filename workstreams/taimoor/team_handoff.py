"""Validate a pinned team corpus and run training-only integration comparisons.

Copies Smit's annotations without replacing their estimates. The sole MIDI
normalization moves terminal end-of-track messages; all other absolute events
must remain identical. This is an engineering handoff, not final evaluation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import time

import mido

from .arranger import Weights, arrange
from .checkpoint import valid
from .evaluate import measure
from .independent_audit import audit_case, melody, parse
from .model import load_song, write_midi


SMIT_REVISION = 'ac9eb64673a4c6cfa086acbda5296f302dbf9ee9'
METHODS = ('instrument_only', 'fixed', 'adaptive', 'no_continuity')
HERE = Path(__file__).parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blob(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def inside(root, relative):
    root = root.resolve()
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError('Input path escapes the pinned checkout')
    return result


def assert_revision(root):
    actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(
        ['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=no'], text=True)
    if actual != SMIT_REVISION or dirty:
        raise ValueError('Use an unchanged checkout at the pinned Smit revision: ' + SMIT_REVISION)


def semantic_events(raw):
    """All absolute MIDI messages except terminal length metadata."""
    result = []
    for track in raw.tracks:
        tick, messages = 0, []
        for message in track:
            tick += message.time
            if message.type != 'end_of_track':
                messages.append((tick, message.copy(time=0).dict()))
        result.append(messages)
    return result


def normalize_endpoints(source, destination, bars):
    raw = mido.MidiFile(source)
    target = bars * 4 * raw.ticks_per_beat
    before = semantic_events(raw)
    changed = []
    for index, track in enumerate(raw.tracks):
        tick, kept, ended = 0, [], False
        for message in track:
            tick += message.time
            if ended:
                raise ValueError('An event follows end_of_track')
            if message.type == 'end_of_track':
                ended = True
                if tick > target + 1:
                    raise ValueError('Trailing end_of_track exceeds the one-tick handoff repair policy')
            else:
                if tick > target:
                    raise ValueError('A musical or control event exceeds the excerpt; refusing to trim it')
                kept.append(message)
        last_event = sum(message.time for message in kept)
        if tick != target:
            changed.append({'track': index, 'original_end_tick': tick, 'normalized_end_tick': target})
        track[:] = kept + [mido.MetaMessage('end_of_track', time=target-last_event)]
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw.save(destination)
    reread = mido.MidiFile(destination)
    if semantic_events(reread) != before:
        raise ValueError('Endpoint normalization changed a musical/control/meta event')
    if any(sum(message.time for message in t) != target for t in reread.tracks):
        raise ValueError('Normalized track endpoint does not match the contract')
    return changed


def composition_key(value):
    # Conservative review grouping, also catching common numeric file variants.
    value = re.sub(r'\.\d+$', '', value.strip().casefold())
    return re.sub(r'[^a-z0-9]', '', value)


def split_conflicts(records):
    conflicts = []
    for key in ('composition_key', 'source_sha256', 'prepared_sha256', 'melody_signature_sha256'):
        groups = defaultdict(list)
        for row in records:
            groups[row[key]].append(row)
        for value, group in groups.items():
            if len({r['split'] for r in group}) > 1:
                conflicts.append({'grouped_by': key, 'value': value,
                                  'cases': [r['case_id'] for r in group],
                                  'splits': sorted({r['split'] for r in group})})
    return conflicts


def prior_exposure(row, source_blob, pilot):
    matches = []
    for case in pilot['cases']:
        exact = source_blob == case['source_git_blob']
        grouped = composition_key(row['source_id']) == composition_key(case['composition_id'])
        if exact or grouped:
            matches.append({'prior_case_id': case['case_id'], 'prior_split': case['split'],
                            'match': 'exact_source_blob' if exact else 'normalized_composition_name'})
    return matches


def write_style_manifest(root, records):
    fields = ['midi_path', 'composition_id', 'genre', 'split', 'melody_track_index', 'case_id']
    with (root / 'style_dataset.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({'midi_path': row['midi'], 'composition_id': row['composition_key'],
                             'genre': row['source_style'],
                             'split': 'validation' if row['split'] == 'val' else row['split'],
                             'melody_track_index': row['melody_track'], 'case_id': row['case_id']})


def prepare(source_root, root):
    source_root, root = source_root.resolve(), root.resolve()
    if root.is_relative_to(source_root):
        raise ValueError('Write handoff outputs outside the pinned teammate checkout')
    if root.exists() and any(root.iterdir()):
        raise ValueError('Use a new, empty output directory; existing handoff evidence is immutable')
    assert_revision(source_root)
    root.mkdir(parents=True, exist_ok=True)
    manifest = source_root / 'data/excerpt_manifest.csv'
    original_manifest = source_root / 'data/dataset_manifest.csv'
    frozen = json.loads((source_root / 'data/manifest_frozen.json').read_text())
    if sha(original_manifest) != frozen['manifest_sha256']:
        raise ValueError('Frozen source manifest hash mismatch')
    rows = list(csv.DictReader(manifest.open(encoding='utf-8')))
    ids = [r['case_id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate case IDs in team manifest')
    pilot_path = HERE / 'pilot_protocol.json'
    pilot = json.loads(pilot_path.read_text())
    records, failures = [], []
    for row in rows:
        try:
            case = row['case_id']
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', case):
                raise ValueError('Unsafe case ID')
            if row['status'] != 'OK' or row['split'] not in ('train', 'val', 'test'):
                raise ValueError('Unresolved crop status or unsupported split')
            if not composition_key(row['source_id']):
                raise ValueError('Composition identity is missing')
            if row['source_style'] not in ('jazz', 'rock') or row['target_style'] != (
                    'jazz' if row['source_style'] == 'rock' else 'rock'):
                raise ValueError('Invalid transfer direction')
            midi = inside(source_root, row['excerpt_path'])
            annotation = midi.with_suffix('.json')
            info = json.loads(annotation.read_text())
            expected = {'case_id': case, 'source_style': row['source_style'], 'split': row['split'],
                        'bars': int(row['crop_bars']), 'melody_track': int(row['excerpt_melody_track'])}
            if any(info.get(k) != v for k, v in expected.items()):
                raise ValueError('Annotation and excerpt manifest disagree')
            if info['midi_path'] != midi.name or midi.name != case + '.mid':
                raise ValueError('Annotation must name the paired case MIDI')
            source = inside(source_root, 'data/' + row['source_style'] + '/' + row['midi_file'])
            if sha(source) != row['sha256']:
                raise ValueError('Original source hash does not match manifest')
            try:
                load_song(annotation)
                original_load = {'passed': True, 'error': None}
            except ValueError as exc:
                original_load = {'passed': False, 'error': str(exc)}
            prepared_midi = root / 'prepared' / midi.name
            changes = normalize_endpoints(midi, prepared_midi, expected['bars'])
            prepared_annotation = prepared_midi.with_suffix('.json')
            prepared_annotation.write_bytes(annotation.read_bytes())
            song = load_song(prepared_annotation)
            if not 30-1e-6 <= song.duration_beats * song.seconds_per_beat <= 60+1e-6:
                raise ValueError('Excerpt is outside the 30-60 second scope')
            raw_source, raw_prepared = parse(midi), parse(prepared_midi)
            if raw_prepared['hanging_notes'] or raw_prepared['orphan_note_offs']:
                raise ValueError('Source crop has unmatched raw note events')
            signature = melody(raw_prepared, song.melody_track)
            if not signature or signature != melody(raw_source, song.melody_track):
                raise ValueError('Selected melody changed during handoff normalization')
            source_blob = blob(source)
            records.append({**expected, 'composition_id': row['source_id'],
                            'composition_key': composition_key(row['source_id']),
                            'source_midi': source.relative_to(source_root).as_posix(),
                            'source_git_blob': source_blob, 'source_sha256': sha(source),
                            'original_excerpt_sha256': sha(midi),
                            'original_annotation_sha256': sha(annotation),
                            'original_loader': original_load, 'endpoint_metadata_changes': changes,
                            'non_endpoint_events_unchanged': True,
                            'annotation': prepared_annotation.relative_to(root).as_posix(),
                            'midi': prepared_midi.relative_to(root).as_posix(),
                            'prepared_sha256': sha(prepared_midi),
                            'annotation_sha256': sha(prepared_annotation),
                            'duration_seconds': song.duration_beats * song.seconds_per_beat,
                            'melody_notes': sum(signature.values()),
                            'melody_signature_sha256': hashlib.sha256(
                                repr(sorted(signature.items())).encode()).hexdigest(),
                            'prior_pilot_matches': prior_exposure(row, source_blob, pilot),
                            'artist': row.get('artist', '').strip(),
                            'annotation_review': 'not_recorded; upstream says automatic estimate',
                            'licence_review': 'not_recorded; upstream says TODO'})
        except Exception as exc:
            failures.append({'case_id': row['case_id'], 'stage': 'prepare',
                             'error': f'{type(exc).__name__}: {exc}'})
    conflicts = split_conflicts(records)
    test_exposure = [r['case_id'] for r in records if r['split'] == 'test' and r['prior_pilot_matches']]
    report = {'scope': 'Team handoff compatibility audit; no model fitting or held-out output generation',
              'source_repository': 'Pyrex111/CSC575_Music_Retrieval_Techniques',
              'source_revision': SMIT_REVISION,
              'manifest_sha256': sha(manifest), 'frozen_manifest_sha256': sha(original_manifest),
              'prior_pilot_protocol_sha256': sha(pilot_path),
              'planned_compositions': len(rows), 'compatible_compositions': len(records),
              'original_loader_passes': sum(r['original_loader']['passed'] for r in records),
              'endpoint_normalized_cases': sum(bool(r['endpoint_metadata_changes']) for r in records),
              'split_counts': dict(Counter(r['split'] for r in records)),
              'direction_counts': dict(Counter(r['source_style'] for r in records)),
              'cross_split_conflicts': conflicts, 'previously_exposed_test_cases': test_exposure,
              'artist_fields_missing': sum(not r['artist'] for r in records),
              'ready_for_confirmatory_evaluation': False,
              'blockers': ['Chord/melody/phrase review has not been recorded.',
                           'Artist/alternate-version grouping and provenance review remain incomplete.',
                           'Earlier-pilot exposure must be resolved or disclosed in the final split protocol.'],
              'runtime': {'python': platform.python_version(), 'platform': platform.platform()},
              'records': records, 'failures': failures}
    write_style_manifest(root, records)
    report['style_manifest_sha256'] = sha(root / 'style_dataset.csv')
    dump(root / 'handoff_audit.json', report)
    print(f"Compatible: {len(records)}/{len(rows)}; original loader: {report['original_loader_passes']}/{len(rows)}; "
          f"previously exposed test compositions: {len(test_exposure)}")
    if failures or conflicts:
        raise SystemExit('Handoff audit recorded unresolved input failures or cross-split conflicts')
    return report


def checked_records(root, *, allow_split_conflicts=False):
    report = json.loads((root / 'handoff_audit.json').read_text())
    if report['source_revision'] != SMIT_REVISION or report['failures']:
        raise ValueError('Handoff audit has an unsupported revision or unresolved failures/conflicts')
    if report['cross_split_conflicts'] and not allow_split_conflicts:
        raise ValueError('Handoff audit has unresolved cross-split conflicts')
    if sha(root / 'style_dataset.csv') != report['style_manifest_sha256']:
        raise ValueError('Style handoff manifest changed after the handoff audit')
    for row in report['records']:
        if sha(inside(root, row['midi'])) != row['prepared_sha256'] or sha(inside(root, row['annotation'])) != row['annotation_sha256']:
            raise ValueError('Prepared MIDI or annotation changed after the handoff audit')
    return report['records']


def training_records(records):
    selected = [r for r in records if r['split'] == 'train']
    if not selected or {r['source_style'] for r in selected} != {'jazz', 'rock'}:
        raise ValueError('Training-only integration needs training cases from both directions')
    return selected


def smoke(root):
    root = root.resolve()
    if (root / 'smoke_results.json').exists() or (root / 'outputs').exists():
        raise ValueError('Existing smoke evidence is immutable; prepare a fresh run directory')
    # A training-only execution check fits no model and can document this
    # integration while the team resolves the proposed validation/test splits.
    records = training_records(checked_records(root, allow_split_conflicts=True))
    audit = json.loads((root / 'handoff_audit.json').read_text())
    weights = Weights(style=1, continuity=4)
    runs, audits, failures = [], [], []
    for record in records:
        song = load_song(root / record['annotation'])
        target = 'jazz' if song.source_style == 'rock' else 'rock'
        for method in METHODS:
            try:
                started = time.perf_counter()
                output, trace = arrange(song, target, method, weights)
                elapsed = time.perf_counter()-started
                path = root / 'outputs' / song.case_id / (method + '.mid')
                write_midi(output, path, song.duration_beats, song.phrases)
                metrics, _ = measure(song, path, trace['melody_track'])
                runs.append({'case_id': song.case_id, 'split': song.split, 'method': method,
                             'target_style': target, 'output': path.relative_to(root).as_posix(),
                             'output_sha256': sha(path), 'technical_pass': valid(metrics, method),
                             'transform_seconds': elapsed, 'metrics': metrics, 'trace': trace})
            except Exception as exc:
                failures.append({'case_id': song.case_id, 'method': method,
                                 'stage': 'arrange', 'error': f'{type(exc).__name__}: {exc}'})
        try:
            audits.extend(audit_case(root / record['annotation'], root / 'outputs'))
        except Exception as exc:
            failures.append({'case_id': song.case_id, 'stage': 'raw_audit',
                             'error': f'{type(exc).__name__}: {exc}'})
    report = {'scope': 'Training-only engineering integration with provisional team annotations',
              'handoff_audit_sha256': sha(root / 'handoff_audit.json'),
              'weights': {'style': 1, 'continuity': 4},
              'weight_policy': 'Prior-pilot settings; no new tuning or final configuration selection',
              'planned_compositions': len(records), 'planned_conditions': len(records)*len(METHODS),
              'validation_or_test_outputs_generated': False,
              'unresolved_cross_split_conflicts': audit['cross_split_conflicts'],
              'final_split_decision_pending': True,
              'code_sha256': {p.name: sha(p) for p in sorted(HERE.glob('*.py'))},
              'runs': runs, 'raw_midi_audit': audits, 'failures': failures,
              'quality_claim': 'No genre-quality or human-listening conclusion'}
    dump(root / 'smoke_results.json', report)
    print(f"Training conditions: {len(runs)}/{report['planned_conditions']}; "
          f"technical passes: {sum(r['technical_pass'] for r in runs)}; "
          f"raw audit passes: {sum(r['technical_pass'] for r in audits)}/{len(audits)}; failures: {len(failures)}")
    if failures or not all(r['technical_pass'] for r in runs + audits):
        raise SystemExit('Training integration recorded a technical failure; inspect saved evidence')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'smoke'))
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.stage == 'prepare':
        if args.source_root is None:
            parser.error('prepare requires --source-root')
        prepare(args.source_root, args.output)
    else:
        smoke(args.output)


if __name__ == '__main__':
    main()
