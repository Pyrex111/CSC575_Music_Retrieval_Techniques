"""Prepare, tune, and evaluate a pinned, composition-separated source-MIDI pilot.

Run prepare, tune, then evaluate, using the same --output directory.
Annotations are explicitly provisional. No human ratings are synthesized.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import time
from urllib.parse import quote
from urllib.request import urlopen

import mido
import numpy as np
import pretty_midi

from .arranger import Weights, arrange
from .evaluate import measure
from .independent_audit import audit_case
from .model import Phrase, load_song, write_midi


HERE = Path(__file__).parent
PROTOCOL = HERE / 'pilot_protocol.json'
FEATURE_BLOB = 'f6c70768cbc5334241dbd1d3f3e9564dfa5a840c'
CHORD_TYPES = [('maj', (0, 4, 7)), ('min', (0, 3, 7)),
               ('7', (0, 4, 7, 10)), ('maj7', (0, 4, 7, 11)),
               ('min7', (0, 3, 7, 10))]
PITCH_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blob_hash(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def source_url(plan, revision, path):
    return f"https://raw.githubusercontent.com/{plan['team_repository']}/{revision}/{quote(path)}"


def obtain(path, url, expected_blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with urlopen(url, timeout=45) as response:
            data = response.read()
        if blob_hash(data) != expected_blob:
            raise ValueError(f'Pinned source hash mismatch: {url}')
        path.write_bytes(data)
    if blob_hash(path.read_bytes()) != expected_blob:
        raise ValueError(f'Existing source hash mismatch: {path}')


def feature_module(root, plan):
    path = root / 'team_code' / 'vinay_style_features.py'
    obtain(path, source_url(plan, plan['vinay_revision'], 'workstreams/vinay/style_features.py'), FEATURE_BLOB)
    spec = importlib.util.spec_from_file_location('pinned_vinay_style_features', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def chroma(midi, melody_index, start, end):
    weights = np.zeros(12)
    bass = np.zeros(12)
    for index, instrument in enumerate(midi.instruments):
        if index == melody_index or instrument.is_drum:
            continue
        for note in instrument.notes:
            overlap = max(0.0, min(end, note.end) - max(start, note.start))
            weight = overlap * (note.velocity / 127)
            weights[note.pitch % 12] += weight
            if note.pitch < 55:
                bass[note.pitch % 12] += weight
    return weights, bass


def chord_guess(weights, bass):
    total = float(weights.sum())
    if total <= 0:
        return None
    ranked = []
    for root in range(12):
        for quality, intervals in CHORD_TYPES:
            pcs = [(root + x) % 12 for x in intervals]
            coverage = float(weights[pcs].sum() / total)
            bass_support = float(bass[root] / bass.sum()) if bass.sum() else 0
            score = coverage + 0.15 * bass_support - 0.035 * (len(intervals) - 3)
            ranked.append((score, root, quality, intervals, coverage))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    best = ranked[0]
    return {'root_pc': best[1], 'intervals': list(best[3]),
            'symbol': PITCH_NAMES[best[1]] + best[2],
            'coverage': best[4], 'score_margin': best[0] - ranked[1][0],
            'alternative': PITCH_NAMES[ranked[1][1]] + ranked[1][2]}


def crop_midi(source, tempo, start_bar, bars, melody_index):
    spb = 60 / tempo
    start, end = start_bar * 4 * spb, (start_bar + bars) * 4 * spb
    output = pretty_midi.PrettyMIDI(initial_tempo=tempo, resolution=source.resolution)
    output.time_signature_changes = [pretty_midi.TimeSignature(4, 4, 0)]
    trimmed = 0
    for index, instrument in enumerate(source.instruments):
        track = pretty_midi.Instrument(instrument.program, is_drum=instrument.is_drum,
                                       name='selected_melody' if index == melody_index else instrument.name or f'source_track_{index}')
        for note in instrument.notes:
            if note.end <= start or note.start >= end:
                continue
            if index == melody_index and (note.start < start or note.end > end):
                trimmed += 1
            track.notes.append(pretty_midi.Note(note.velocity, note.pitch,
                               max(start, note.start) - start, min(end, note.end) - start))
        # Carry the controller state at the crop boundary, then preserve in-crop events.
        for number in sorted({x.number for x in instrument.control_changes}):
            prior = [x for x in instrument.control_changes if x.number == number and x.time < start]
            if prior:
                track.control_changes.append(pretty_midi.ControlChange(number, max(prior, key=lambda x: x.time).value, 0))
        track.control_changes += [pretty_midi.ControlChange(x.number, x.value, x.time-start)
                                  for x in instrument.control_changes if start <= x.time < end]
        prior = [x for x in instrument.pitch_bends if x.time < start]
        if prior:
            track.pitch_bends.append(pretty_midi.PitchBend(max(prior, key=lambda x: x.time).pitch, 0))
        track.pitch_bends += [pretty_midi.PitchBend(x.pitch, x.time-start)
                             for x in instrument.pitch_bends if start <= x.time < end]
        output.instruments.append(track)
    # Empty instruments are omitted by MIDI serialization; record the resulting index.
    new_melody_index = sum(bool(x.notes) for x in output.instruments[:melody_index])
    return output, new_melody_index, trimmed


def phrase_grid(midi, melody_index, spb, bars):
    seen, phrases = {}, []
    for start in range(0, bars, 4):
        signature = tuple(sorted((n.pitch, round(n.start/spb-start*4, 5), round((n.end-n.start)/spb, 5))
                                 for n in midi.instruments[melody_index].notes if start*4 <= n.start/spb < (start+4)*4))
        if signature not in seen:
            seen[signature] = f'P{len(seen)+1}'
        phrases.append(Phrase(seen[signature], start, 4))
    return tuple(phrases)


def prepare(root, plan):
    if (root / 'preparation.json').exists():
        raise ValueError('Preparation already exists; use a new output directory to create a new protocol run.')
    records, failures = [], []
    for item in plan['cases']:
        try:
            source_path = root / 'source_midi' / item['path']
            url = source_url(plan, plan['source_revision'], item['path'])
            obtain(source_path, url, item['source_git_blob'])
            raw = mido.MidiFile(source_path)
            source = pretty_midi.PrettyMIDI(str(source_path))
            tempi = source.get_tempo_changes()[1]
            if len(tempi) != 1 or any(s.numerator != 4 or s.denominator != 4 for s in source.time_signature_changes):
                raise ValueError('Source is outside constant-tempo 4/4 scope')
            tempo = float(tempi[0])
            if not 30 - 1e-6 <= item['bars'] * 240 / tempo <= 60 + 1e-6:
                raise ValueError('Excerpt duration outside 30-60 seconds')
            if (item['start_bar'] + item['bars']) * 240 / tempo > source.get_end_time():
                raise ValueError('Crop exceeds source note duration')
            crop, melody_index, trimmed = crop_midi(source, tempo, item['start_bar'], item['bars'], item['melody_track'])
            directory = root / 'prepared'
            path = directory / (item['case_id'] + '.mid')
            write_midi(crop, path, item['bars'] * 4)
            crop = pretty_midi.PrettyMIDI(str(path))
            spb = 60 / tempo
            if len(crop.instruments[melody_index].notes) < 8:
                raise ValueError('Too few melody notes in selected crop')
            phrases = phrase_grid(crop, melody_index, spb, item['bars'])
            write_midi(crop, path, item['bars'] * 4, phrases)
            chords, diagnostics = [], []
            for bar in range(item['bars']):
                start, end = bar * 4 * spb, (bar+1) * 4 * spb
                guess = chord_guess(*chroma(crop, melody_index, start, end))
                if guess is None:
                    raise ValueError(f'No pitched accompaniment for chord estimate at bar {bar+1}')
                halves = [chord_guess(*chroma(crop, melody_index, a, b))
                          for a, b in [(start, start+2*spb), (start+2*spb, end)]]
                different = all(halves) and (halves[0]['root_pc'], halves[0]['intervals']) != (halves[1]['root_pc'], halves[1]['intervals'])
                chords.append({k: guess[k] for k in ['root_pc', 'intervals']})
                diagnostics.append({'bar': bar+1, **guess, 'half_bar_disagreement': bool(different),
                                    'needs_human_review': guess['coverage'] < 0.85 or guess['score_margin'] < 0.08 or bool(different)})
            annotation = {'schema_version': 1, **{k: item[k] for k in ['case_id','composition_id','source_style','split','bars']},
                          'midi_path': path.name, 'melody_track': melody_index, 'tempo_bpm': tempo,
                          'time_signature': [4,4], 'phrases': [asdict(p) for p in phrases], 'chords': chords,
                          'provenance': {'source_url': url, 'source_revision': plan['source_revision'],
                                         'source_sha256': sha(source_path), 'source_git_blob': item['source_git_blob'],
                                         'start_bar_zero_based': item['start_bar'],
                                         'source_melody_track_index': item['melody_track'],
                                         'source_melody_track_name': source.instruments[item['melody_track']].name,
                                         'boundary_trimmed_melody_notes': trimmed},
                          'annotation_status': 'provisional_computational; not independently musician-reviewed',
                          'phrase_policy': 'Four-bar grid; exact repeated melody signatures share labels; musical boundaries not independently reviewed',
                          'chord_diagnostics': diagnostics}
            annotation_path = path.with_suffix('.json')
            dump(annotation_path, annotation)
            song = load_song(annotation_path)
            melody_signature = [(n.pitch, round(n.start/spb,5), round(n.end/spb,5)) for n in song.melody.notes]
            record = {**item, 'annotation': annotation_path.relative_to(root).as_posix(),
                      'source_sha256': sha(source_path), 'prepared_sha256': sha(path),
                      'annotation_sha256': sha(annotation_path), 'duration_seconds': item['bars']*4*spb,
                      'melody_notes': len(song.melody.notes), 'melody_signature_sha256': hashlib.sha256(repr(melody_signature).encode()).hexdigest(),
                      'flagged_bars': sum(d['needs_human_review'] for d in diagnostics),
                      'mean_chord_coverage': float(np.mean([d['coverage'] for d in diagnostics])),
                      'boundary_trimmed_melody_notes': trimmed}
            records.append(record)
        except Exception as exc:
            failures.append({'case_id': item['case_id'], 'stage': 'prepare', 'error': f'{type(exc).__name__}: {exc}'})
    # Do not silently remove failed planned cases from the study denominator.
    for key in ['composition_id', 'source_sha256', 'prepared_sha256', 'melody_signature_sha256']:
        values = [r[key] for r in records]
        if len(values) != len(set(values)):
            raise ValueError(f'Duplicate source/composition content: {key}')
    report = {'protocol_sha256': sha(PROTOCOL), 'planned_cases': len(plan['cases']),
              'annotation_limitations': plan['annotation_policy'], 'prepared': records, 'failures': failures,
              'source_provenance_limit': 'Smit branch files and genre folders; upstream acquisition/redistribution terms and independent genre review not supplied in that branch.',
              'runtime': {'python': platform.python_version(), 'platform': platform.platform()}}
    dump(root / 'preparation.json', report)
    dump(root / 'protocol.json', plan)
    fields = ['case_id','bar','symbol','alternative','coverage','score_margin','half_bar_disagreement','needs_human_review','reviewed_symbol','reviewer_note']
    with (root/'annotation_review.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            data = json.loads((root/record['annotation']).read_text())
            for d in data['chord_diagnostics']:
                writer.writerow({**{k:d[k] for k in fields if k in d}, 'case_id':record['case_id']})
    print(f"Prepared {len(records)}/{len(plan['cases'])} compositions; {len(failures)} preparation failures")
    if failures:
        raise SystemExit('Preparation failures are recorded; resolve explicitly before tuning/evaluation.')


def code_hashes():
    return {p.name: sha(p) for p in sorted(HERE.glob('*.py'))}


def validated_records(root, plan):
    preparation = json.loads((root/'preparation.json').read_text())
    if preparation['protocol_sha256'] != sha(PROTOCOL) or preparation['failures']:
        raise ValueError('Protocol changed or preparation has unresolved failures')
    for record in preparation['prepared']:
        annotation = root/record['annotation']
        if sha(annotation) != record['annotation_sha256'] or sha(annotation.with_suffix('.mid')) != record['prepared_sha256']:
            raise ValueError('Prepared input changed after preparation')
    return preparation['prepared']


def descriptor(module, midi, melody_index, tempo):
    features = module.extract_style_features(midi, melody_index)
    return np.array([features['note_density'], features['average_polyphony'],
                     features['offbeat_activity'], features['average_note_duration']*tempo/60], dtype=float)


def boundary_metrics(midi, melody_index, song):
    tracks = [i for index,i in enumerate(midi.instruments) if index != melody_index]
    counts = []
    jumps = []
    spb = song.seconds_per_beat
    bass = [n for i in tracks if not i.is_drum and (i.name.lower() == 'bass' or 32 <= i.program <= 39) for n in i.notes]
    for phrase in song.phrases:
        a,b=phrase.start_bar*4,(phrase.start_bar+phrase.bars)*4
        counts.append(sum(a <= n.start/spb < b for i in tracks for n in i.notes)/phrase.bars)
    for phrase in song.phrases[1:]:
        boundary=phrase.start_bar*4*spb
        prior=[n for n in bass if n.start < boundary-1e-7]
        following=[n for n in bass if n.start >= boundary-1e-7]
        if prior and following:
            jumps.append(abs(max(prior,key=lambda n:n.start).pitch-min(following,key=lambda n:n.start).pitch))
    return {'phrase_notes_per_bar':counts,
            'mean_phrase_texture_change_notes_per_bar':float(np.mean(np.abs(np.diff(counts)))) if len(counts)>1 else 0.0,
            'boundary_bass_jumps_semitones':jumps,
            'mean_boundary_bass_jump_semitones':float(np.mean(jumps)) if jumps else 0.0,
            'max_boundary_bass_jump_semitones':max(jumps,default=0)}


def references(root, records, module):
    vectors = {'jazz':[], 'rock':[]}
    for record in records:
        if record['split'] != 'development':
            continue
        song = load_song(root/record['annotation'])
        vectors[song.source_style].append(descriptor(module,song.midi,song.melody_track,song.tempo))
    floors = np.array(json.loads(PROTOCOL.read_text())['descriptor_scale_floor'])
    all_values = np.vstack([v for values in vectors.values() for v in values])
    scale = np.maximum(np.std(all_values,axis=0),floors)
    return {'centers':{style:np.mean(values,axis=0).tolist() for style,values in vectors.items()},
            'scale':scale.tolist(), 'reference_cases':[r['case_id'] for r in records if r['split']=='development']}


def distance(vector, target, refs):
    return float(np.sqrt(np.mean(((vector-np.array(refs['centers'][target]))/np.array(refs['scale']))**2)))


def valid(metrics, method):
    invariants = all(metrics[k] for k in ['melody_preserved','duration_preserved','phrase_markers_preserved','tempo_preserved','time_signature_preserved'])
    return bool(invariants and metrics['event_bounds_violations']==0 and (method=='instrument_only' or
                metrics['harmony_pitch_class_violations']==metrics['register_violations']==0))


def tune(root, plan):
    if (root/'frozen_selection.json').exists():
        raise ValueError('A frozen selection already exists; never overwrite it after seeing test outputs.')
    records = validated_records(root,plan)
    module = feature_module(root,plan)
    refs = references(root,records,module)
    development = [r for r in records if r['split']=='development']
    grid = []
    for continuity in plan['continuity_grid']:
        rows = []
        for record in development:
            song=load_song(root/record['annotation']); target='jazz' if song.source_style=='rock' else 'rock'
            midi,trace=arrange(song,target,weights=Weights(plan['style_weight'],continuity))
            path=root/'development_grid'/str(continuity)/f'{song.case_id}.mid'
            write_midi(midi,path,song.duration_beats,song.phrases)
            metrics,_=measure(song,path,trace['melody_track'])
            output=pretty_midi.PrettyMIDI(str(path))
            vector=descriptor(module,output,trace['melody_track'],song.tempo)
            musical=boundary_metrics(output,trace['melody_track'],song)
            d=distance(vector,target,refs)
            rows.append({'case_id':song.case_id,'technical_pass':valid(metrics,'adaptive'),
                         'descriptor_distance':d, 'boundary_bass_jump_semitones':musical['mean_boundary_bass_jump_semitones'],
                         'selection_proxy':d+0.25*musical['mean_boundary_bass_jump_semitones']/12,
                         'plans':[x['plan'] for x in trace['selection']], 'output_sha256':sha(path)})
        eligible=all(r['technical_pass'] for r in rows)
        grid.append({'continuity':continuity,'style':plan['style_weight'],'eligible':eligible,
                     'mean_selection_proxy':float(np.mean([r['selection_proxy'] for r in rows])) if eligible else None,
                     'per_composition':rows})
    eligible=[g for g in grid if g['eligible']]
    if not eligible:
        raise ValueError('No configuration passes development technical checks')
    best=min(eligible,key=lambda g:(g['mean_selection_proxy'],g['continuity']))
    selection={'protocol_sha256':sha(PROTOCOL),'code_sha256':code_hashes(),
               'input_hashes':{r['case_id']:r['annotation_sha256'] for r in records},
               'selected_weights':{'style':best['style'],'continuity':best['continuity']},
               'selection_rule':plan['selection_rule'],'development_cases':[r['case_id'] for r in development],
               'test_cases':[r['case_id'] for r in records if r['split']=='test'],
               'target_references':refs,'feature_code_git_blob':FEATURE_BLOB,
               'grid':grid,'quality_claim':'Development proxy selection only; no perceptual quality claim or test-based tuning.'}
    dump(root/'frozen_selection.json',selection)
    print('Frozen weights:',best['style'],best['continuity'],'selection SHA256:',sha(root/'frozen_selection.json'))


def evaluate(root,plan):
    if (root/'evaluation.json').exists():
        raise ValueError('Evaluation already exists; use saved outputs rather than retuning on test results.')
    records=validated_records(root,plan)
    frozen=json.loads((root/'frozen_selection.json').read_text())
    if frozen['code_sha256'] != code_hashes() or frozen['protocol_sha256'] != sha(PROTOCOL):
        raise ValueError('Evaluation code/protocol changed after development selection')
    if frozen['input_hashes'] != {r['case_id']:r['annotation_sha256'] for r in records}:
        raise ValueError('Input set changed after selection')
    module=feature_module(root,plan)
    weights=Weights(**frozen['selected_weights'])
    rows,failures,audits=[],[],[]
    started=time.perf_counter()
    for record in records:
        song=load_song(root/record['annotation']);target='jazz' if song.source_style=='rock' else 'rock'
        signatures={}
        for method in plan['methods']:
            try:
                tick=time.perf_counter()
                midi,trace=arrange(song,target,method,weights)
                elapsed=time.perf_counter()-tick
                path=root/'outputs'/song.case_id/f'{method}.mid'
                write_midi(midi,path,song.duration_beats,song.phrases)
                metrics,signature=measure(song,path,trace['melody_track'])
                signatures[method]=signature
                output=pretty_midi.PrettyMIDI(str(path))
                vector=descriptor(module,output,trace['melody_track'],song.tempo)
                rows.append({'case_id':song.case_id,'composition_id':record['composition_id'],
                             'split':song.split,'source_style':song.source_style,'target_style':target,
                             'method':method,'output':path.relative_to(root).as_posix(),'output_sha256':sha(path),
                             'annotation_sha256':record['annotation_sha256'],'transform_seconds':elapsed,
                             'technical_pass':valid(metrics,method),'metrics':metrics,'trace':trace,
                             'descriptor_vector':vector.tolist(),
                             'target_reference_distance':distance(vector,target,frozen['target_references']),
                             'musical_measurements':boundary_metrics(output,trace['melody_track'],song),
                             'generated_harmony_register_constraints_applicable':method!='instrument_only'})
            except Exception as exc:
                failures.append({'case_id':song.case_id,'method':method,'stage':'evaluate','error':f'{type(exc).__name__}: {exc}'})
        for row in [r for r in rows if r['case_id']==song.case_id]:
            if 'fixed' in signatures:
                row['accompaniment_events_different_from_fixed']=sum((signatures[row['method']]-signatures['fixed']).values())+sum((signatures['fixed']-signatures[row['method']]).values())
        try:
            audits.extend(audit_case(root/record['annotation'],root/'outputs'))
        except Exception as exc:
            failures.append({'case_id':song.case_id,'stage':'raw_midi_audit','error':f'{type(exc).__name__}: {exc}'})
    report={'scope':'Source-derived, composition-separated exploratory pilot with provisional annotations',
            'planned_compositions':len(plan['cases']),'planned_conditions':len(plan['cases'])*len(plan['methods']),
            'selection_sha256':sha(root/'frozen_selection.json'),'protocol_sha256':sha(PROTOCOL),
            'weights':frozen['selected_weights'],'code_sha256':code_hashes(),
            'elapsed_seconds':time.perf_counter()-started,'runs':rows,'failures':failures,
            'raw_midi_audit':audits,
            'limitations':['Chord map and four-bar boundaries are computational approximations, pending independent musical review.',
                           'Genre labels are inherited from Smit folder names; no new independent genre labeling is claimed.',
                           'Eight test compositions form a convenience pilot, not the original 20-test-composition protocol.',
                           'Target-reference descriptor distance is a proxy, not genre accuracy or listener preference.',
                           'No listener responses have been collected; synthetic negative controls are reported separately.']}
    dump(root/'evaluation.json',report)
    print(f"Evaluated {len(rows)}/{report['planned_conditions']} conditions; technical passes {sum(r['technical_pass'] for r in rows)}; raw audit passes {sum(r['technical_pass'] for r in audits)}/{len(audits)}; failures {len(failures)}")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','tune','evaluate'])
    parser.add_argument('--output',type=Path,default=Path('results/local/taimoor_checkpoint'))
    args=parser.parse_args()
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=True)
    plan=json.loads(PROTOCOL.read_text())
    {'prepare':prepare,'tune':tune,'evaluate':evaluate}[args.stage](root,plan)


if __name__=='__main__':
    main()
