"""Audit saved MIDI using raw events, without importing the generator or its evaluator.

Run: python -m workstreams.taimoor.independent_audit --results results/local/taimoor
This verifies technical properties only. It does not classify genre or rate music.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from statistics import mean

import mido


def parse(path):
    midi = mido.MidiFile(path)
    notes, names, tempos, signatures, markers = [], {}, [], [], []
    hanging = orphan_offs = 0
    for index, track in enumerate(midi.tracks):
        tick, active = 0, defaultdict(deque)
        for event in track:
            tick += event.time
            beat = Fraction(tick, midi.ticks_per_beat)
            if event.type == 'track_name':
                names[index] = event.name
            elif event.type == 'set_tempo':
                tempos.append((beat, event.tempo))
            elif event.type == 'time_signature':
                signatures.append((beat, event.numerator, event.denominator))
            elif event.type == 'marker':
                markers.append((beat, event.text))
            elif event.type == 'note_on' and event.velocity:
                active[(event.channel, event.note)].append((beat, event.velocity))
            elif event.type in ('note_on', 'note_off'):
                key = (event.channel, event.note)
                if not active[key]:
                    orphan_offs += 1
                    continue
                start, velocity = active[key].popleft()
                notes.append((index, event.channel, event.note, start, beat, velocity))
        hanging += sum(len(queue) for queue in active.values())
    return {'notes': notes, 'names': names, 'tempos': tempos or [(Fraction(0), 500000)],
            'signatures': signatures or [(Fraction(0), 4, 4)], 'markers': sorted(markers),
            'hanging_notes': hanging, 'orphan_note_offs': orphan_offs,
            'duration_seconds': midi.length, 'ticks_per_beat': midi.ticks_per_beat,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def melody(data):
    ids = [index for index, name in data['names'].items() if name == 'selected_melody']
    if len(ids) != 1:
        raise ValueError('Fixture audit requires one track named selected_melody')
    # Ignore channel reassignment, but compare exact beat positions and velocities.
    return Counter((pitch, start, end, velocity)
                   for track, _, pitch, start, end, velocity in data['notes'] if track == ids[0])


def audit_case(annotation, root):
    info = json.loads(annotation.read_text(encoding='utf-8'))
    source = parse(annotation.parent/info['midi_path'])
    source_melody = melody(source)
    expected_markers = sorted((Fraction(p['start_bar']*4), p['label']) for p in info['phrases'])
    rows = []
    for method in ('instrument_only', 'fixed', 'adaptive', 'no_continuity'):
        path = root/info['case_id']/f'{method}.mid'
        output = parse(path)
        output_melody = melody(output)
        changes = sum((source_melody-output_melody).values()) + sum((output_melody-source_melody).values())
        melody_id = next(i for i, name in output['names'].items() if name == 'selected_melody')
        chord_violations = range_violations = bounds_violations = 0
        note_counts = [0 for _ in info['phrases']]
        for track, channel, pitch, start, end, _ in output['notes']:
            if start < 0 or end <= start or end > info['bars']*4:
                bounds_violations += 1
            if track == melody_id:
                continue
            for i, phrase in enumerate(info['phrases']):
                if phrase['start_bar']*4 <= start < (phrase['start_bar']+phrase['bars'])*4:
                    note_counts[i] += 1
            if channel != 9:
                chord = info['chords'][min(len(info['chords'])-1, int(start//4))]
                chord_violations += (pitch-chord['root_pc']) % 12 not in chord['intervals']
                register = (36, 60) if output['names'].get(track) == 'bass' else (48, 84)
                range_violations += not register[0] <= pitch <= register[1]
        densities = [count/p['bars'] for count, p in zip(note_counts, info['phrases'])]
        texture_change = mean(abs(a-b) for a, b in zip(densities, densities[1:])) if len(densities) > 1 else 0
        expected_duration = info['bars']*4*60/info['tempo_bpm']
        row = {'case_id': info['case_id'], 'method': method,
               'source_sha256': source['sha256'], 'output_sha256': output['sha256'],
               'melody_notes': sum(output_melody.values()), 'melody_event_differences': changes,
               'duration_seconds': output['duration_seconds'],
               'duration_preserved': abs(output['duration_seconds']-source['duration_seconds']) < 1e-6,
               'annotation_duration_agreement_within_one_tick': abs(output['duration_seconds']-expected_duration) <= (source['tempos'][0][1]/1e6)/source['ticks_per_beat'] + 1e-8,
               'tempo_preserved': output['tempos'] == source['tempos'],
               'metre_preserved': output['signatures'] == source['signatures'],
               'markers_preserved': output['markers'] == expected_markers,
               'unmatched_note_events': output['hanging_notes']+output['orphan_note_offs'],
               'chord_membership_violations': int(chord_violations),
               'register_violations': int(range_violations), 'bounds_violations': bounds_violations,
               'accompaniment_notes_per_bar_by_phrase': densities,
               'mean_phrase_texture_change_notes_per_bar': texture_change}
        row['generated_harmony_register_constraints_applicable'] = method != 'instrument_only'
        row['technical_pass'] = changes == 0 and all(row[key] for key in (
            'duration_preserved', 'tempo_preserved', 'metre_preserved', 'markers_preserved')) and all(
                row[key] == 0 for key in ('unmatched_note_events', 'bounds_violations')) and (
                    method == 'instrument_only' or
                    (row['chord_membership_violations'] == 0 and row['register_violations'] == 0))
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    args = parser.parse_args()
    root = args.results.resolve()
    annotations = sorted((root/'fixtures').glob('*.json'))
    if not annotations:
        raise SystemExit('No generated fixture annotation JSON found in results/fixtures')
    rows = [row for annotation in annotations for row in audit_case(annotation, root)]
    report = {'scope': 'Raw-MIDI technical audit of synthetic fixtures; no genre-quality conclusion',
              'independence': 'Uses mido directly; does not import arranger.py, model.py, or evaluate.py.',
              'runs': rows}
    (root/'independent_audit.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    lines = ['# Independent raw-MIDI audit', '', report['scope'], '',
             '| Case | Method | Melody event differences | Technical check | Mean phrase texture change (notes/bar) |',
             '| --- | --- | --- | --- | --- |']
    for row in rows:
        lines.append(f'| {row["case_id"]} | {row["method"]} | {row["melody_event_differences"]} | '
                     f'{"pass" if row["technical_pass"] else "FAIL"} | '
                     f'{row["mean_phrase_texture_change_notes_per_bar"]:.2f} |')
    lines += ['', 'Texture change is descriptive, not an independent musical-quality score. Fewer changes are not always preferable.',
              'The audit compares note events, not sustained-pedal acoustic tails or rendered audio. Genre and listener preference remain untested.']
    (root/'independent_audit.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    passed = sum(row['technical_pass'] for row in rows)
    print(f'{passed}/{len(rows)} technical passes; zero-event difference means exact pitch/on/off/velocity agreement in beat coordinates.')
    for row in rows:
        if row['method'] in ('adaptive', 'no_continuity'):
            print(row['case_id'],row['method'],'texture change:',round(row['mean_phrase_texture_change_notes_per_bar'],2))
    if passed != len(rows):
        raise SystemExit('Independent audit found a technical failure')


if __name__ == '__main__':
    main()
