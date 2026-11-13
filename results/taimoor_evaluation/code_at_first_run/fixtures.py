"""Generate original synthetic fixtures, not downloaded songs or genre ground truth."""
from pathlib import Path
import json

import pretty_midi

from .arranger import PALETTES, adapt, patterns
from .model import Chord, Phrase, write_midi


def make_fixtures(destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    configs = [
        ('development_rock', 'rock', 'development', 120, 0, 0),
        ('development_jazz', 'jazz', 'development', 120, 2, 1),
        ('verification_rock', 'rock', 'verification', 80, 5, 2),
        ('verification_jazz', 'jazz', 'verification', 80, 7, 3),
    ]
    paths = []
    for case_id, style, split, tempo, transpose, variant in configs:
        midi = pretty_midi.PrettyMIDI(initial_tempo=tempo, resolution=960)
        midi.time_signature_changes = [pretty_midi.TimeSignature(4, 4, 0)]
        melody = pretty_midi.Instrument(73, name='selected_melody')
        phrases = tuple(Phrase(label, i*4, 4) for i, label in enumerate(('A', 'B', 'A', 'C')))
        roots = [(x+transpose) % 12 for x in (0, 5, 7, 0, 9, 2, 7, 0, 0, 5, 7, 0, 5, 7, 0, 0)]
        chords = tuple(Chord(root, (0, 3, 7) if i in (4, 5) else (0, 4, 7))
                       for i, root in enumerate(roots))
        # A repeats exactly. Other phrases vary rhythmic activity and contour.
        attacks = (2, 12, 2, 8)
        for bar in range(16):
            count = attacks[bar//4]
            for i in range(count):
                relative = i*4/count
                chord = chords[bar]
                degree = (i*(variant+1) + bar%4) % len(chord.intervals)
                pitch = 72 + chord.root_pc + chord.intervals[degree]
                start = bar*4 + relative
                length = 4/count*0.8
                if bar == 15 and i == count-1:
                    length = 64-start  # Explicit 32- or 48-second excerpt endpoint.
                melody.notes.append(pretty_midi.Note(90, pitch, start*60/tempo, (start+length)*60/tempo))
        midi.instruments.append(melody)
        tracks = {'bass': pretty_midi.Instrument(PALETTES[style][0], name='bass'),
                  'chords': pretty_midi.Instrument(PALETTES[style][1], name='chords'),
                  'drums': pretty_midi.Instrument(0, is_drum=True, name='drums')}
        pattern = patterns(style)[1]
        for bar, chord in enumerate(chords):
            for event in adapt(pattern, chord, bar):
                tracks[event.role].notes.append(pretty_midi.Note(
                    event.velocity, event.pitch, event.start*60/tempo,
                    (event.start+event.duration)*60/tempo))
        midi.instruments.extend(tracks.values())
        write_midi(midi, destination/f'{case_id}.mid', 64, phrases)
        data = {
            'schema_version': 1, 'case_id': case_id, 'source_style': style, 'split': split,
            'provenance': 'Original, programmatically authored engineering fixture; not a real song or genre label benchmark.',
            'midi_path': f'{case_id}.mid', 'melody_track': 0, 'tempo_bpm': tempo,
            'time_signature': [4, 4], 'bars': 16,
            'chords': [{'root_pc': c.root_pc, 'intervals': list(c.intervals)} for c in chords],
            'phrases': [{'label': p.label, 'start_bar': p.start_bar, 'bars': p.bars} for p in phrases],
        }
        path = destination/f'{case_id}.json'
        path.write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
        paths.append(path)
    return paths
