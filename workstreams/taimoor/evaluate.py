"""Reopen exported MIDI before measuring invariants and accompaniment behaviour."""
from collections import Counter
from pathlib import Path

import mido
import pretty_midi

from .arranger import RANGES
from .model import Song


def events(track, seconds_per_beat: float):
    return sorted((n.pitch, n.start/seconds_per_beat, (n.end-n.start)/seconds_per_beat)
                  for n in track.notes)


def markers(path: Path):
    raw = mido.MidiFile(path)
    result = []
    for track in raw.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == 'marker':
                result.append((tick/raw.ticks_per_beat, msg.text))
    return sorted(result)


def measure(song: Song, path: Path, melody_track: int):
    raw = mido.MidiFile(path)
    source_raw = mido.MidiFile(song.midi_path)
    source_tempos = [m.tempo for t in source_raw.tracks for m in t if m.type == 'set_tempo'] or [500000]
    output_tempos = [m.tempo for t in raw.tracks for m in t if m.type == 'set_tempo'] or [500000]
    # MIDI encodes integer microseconds per beat. A BPM float may differ slightly;
    # using it to choose a chord bar can put an exact downbeat in the previous bar.
    source_spb, output_spb = source_tempos[0]/1e6, output_tempos[0]/1e6
    output = pretty_midi.PrettyMIDI(str(path))
    original = events(song.melody, source_spb)
    actual = events(output.instruments[melody_track], output_spb)
    tolerance = 1/song.midi.resolution + 1e-8
    same_length = len(original) == len(actual)
    pitch_errors = sum(a[0] != b[0] for a, b in zip(original, actual))
    timing_error = max((max(abs(a[1]-b[1]), abs(a[2]-b[2])) for a, b in zip(original, actual)), default=0)
    harmony_errors = range_errors = bounds_errors = 0
    signatures, densities = Counter(), {}
    for index, instrument in enumerate(output.instruments):
        role = 'melody' if index == melody_track else instrument.name
        densities[role] = len(instrument.notes)/song.duration_beats
        for note in instrument.notes:
            beat = note.start/output_spb
            end = note.end/output_spb
            if beat < -tolerance or end > song.duration_beats+tolerance or end <= beat:
                bounds_errors += 1
            if index == melody_track:
                continue
            signatures[(role, note.pitch, round(beat, 5), round(end, 5))] += 1
            if not instrument.is_drum:
                bar = min(song.bars-1, int((beat+1e-7)//4))
                chord = song.chords[bar]
                if (note.pitch-chord.root_pc) % 12 not in chord.intervals:
                    harmony_errors += 1
                if role in RANGES and not RANGES[role][0] <= note.pitch <= RANGES[role][1]:
                    range_errors += 1
    expected_markers = sorted((p.start_bar*4, p.label) for p in song.phrases)
    tempo_times, tempi = output.get_tempo_changes()
    return {
        'melody_preserved': bool(same_length and pitch_errors == 0 and timing_error <= tolerance),
        'melody_notes': len(actual), 'melody_pitch_errors': pitch_errors,
        'max_melody_timing_error_beats': timing_error,
        'duration_seconds': raw.length,
        'duration_preserved': abs(raw.length-source_raw.length) <= tolerance*source_spb,
        'phrase_markers_preserved': markers(path) == expected_markers,
        'tempo_preserved': bool(len(set(output_tempos)) == 1 and set(output_tempos) == set(source_tempos)),
        'time_signature_preserved': bool(output.time_signature_changes) and all(
            x.numerator == 4 and x.denominator == 4 for x in output.time_signature_changes),
        'harmony_pitch_class_violations': harmony_errors,
        'register_violations': range_errors, 'event_bounds_violations': bounds_errors,
        'note_density_per_beat': densities,
    }, signatures
