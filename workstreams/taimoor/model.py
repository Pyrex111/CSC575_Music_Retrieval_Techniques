"""Version-1 interchange contract: beats, reviewed per-bar chords, phrases.

Only constant-tempo 4/4 MIDI is accepted. No melody/chord inference occurs.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import json
import math
from pathlib import Path
import re

import mido
import pretty_midi


@dataclass(frozen=True)
class Chord:
    root_pc: int
    intervals: tuple[int, ...]


@dataclass(frozen=True)
class Phrase:
    label: str
    start_bar: int
    bars: int


@dataclass
class Song:
    case_id: str
    source_style: str
    split: str
    tempo: float
    bars: int
    melody_track: int
    chords: tuple[Chord, ...]
    phrases: tuple[Phrase, ...]
    midi: pretty_midi.PrettyMIDI
    annotation_path: Path
    midi_path: Path

    @property
    def seconds_per_beat(self) -> float:
        return 60.0 / self.tempo

    @property
    def duration_beats(self) -> int:
        return self.bars * 4

    @property
    def melody(self):
        return self.midi.instruments[self.melody_track]


def integer(value, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def load_song(annotation: str | Path) -> Song:
    path = Path(annotation).resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported annotation schema_version')
    if not isinstance(data.get('case_id'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', data['case_id']):
        raise ValueError('case_id must be a safe filename identifier, without directory separators')
    tempo = float(data['tempo_bpm'])
    if not math.isfinite(tempo) or tempo <= 0:
        raise ValueError('tempo_bpm must be positive and finite')
    bars = integer(data['bars'], 'bars', 1)
    melody_track = integer(data['melody_track'], 'melody_track')
    if data.get('time_signature') != [4, 4]:
        raise ValueError('Only 4/4 is supported')
    if data['source_style'] not in ('jazz', 'rock'):
        raise ValueError('source_style must be jazz or rock')
    chords = []
    for item in data['chords']:
        root = integer(item['root_pc'], 'root_pc')
        intervals = tuple(integer(x, 'chord interval') for x in item['intervals'])
        if root > 11 or len(intervals) < 3 or 0 not in intervals:
            raise ValueError('Chords need root_pc 0..11 and at least three tones including 0')
        if len(set(x % 12 for x in intervals)) != len(intervals) or max(intervals) > 11:
            raise ValueError('Chord intervals must be distinct pitch classes 0..11')
        chords.append(Chord(root, intervals))
    if len(chords) != bars:
        raise ValueError('Provide exactly one reviewed chord per bar')
    phrases, cursor, label_lengths = [], 0, {}
    for item in data['phrases']:
        label = item['label']
        if not isinstance(label, str) or not label:
            raise ValueError('Phrase labels must be nonempty strings')
        start = integer(item['start_bar'], 'start_bar')
        length = integer(item['bars'], 'phrase bars', 1)
        if start != cursor:
            raise ValueError('Phrases must cover the excerpt contiguously without overlap')
        if label in label_lengths and label_lengths[label] != length:
            raise ValueError('Repeated phrase labels must have the same number of bars')
        label_lengths[label] = length
        phrases.append(Phrase(label, start, length))
        cursor += length
    if cursor != bars:
        raise ValueError('Phrase coverage must equal bars')
    midi_path = (path.parent / data['midi_path']).resolve()
    raw = mido.MidiFile(midi_path)
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    if raw.type == 2:
        raise ValueError('Asynchronous type-2 MIDI is unsupported')
    tempos = [msg.tempo for track in raw.tracks for msg in track if msg.type == 'set_tempo']
    expected_tempo = mido.bpm2tempo(tempo)
    if any(abs(t - expected_tempo) > 1 for t in tempos) or (not tempos and tempo != 120):
        raise ValueError('MIDI tempo must be constant and match tempo_bpm')
    if any(msg.numerator != 4 or msg.denominator != 4 for track in raw.tracks
           for msg in track if msg.type == 'time_signature'):
        raise ValueError('MIDI metre must remain 4/4')
    if melody_track >= len(midi.instruments) or midi.instruments[melody_track].is_drum:
        raise ValueError('melody_track must select a pitched instrument')
    melody = midi.instruments[melody_track]
    if not melody.notes:
        raise ValueError('Selected melody has no notes')
    seconds_per_beat = 60 / tempo
    end = bars * 4 * seconds_per_beat
    tolerance = seconds_per_beat / midi.resolution
    if any(n.start < 0 or n.end <= n.start or n.end > end + tolerance for n in melody.notes):
        raise ValueError('Melody notes must fit inside the annotated excerpt')
    if abs(raw.length - end) > tolerance:
        raise ValueError('MIDI end time must match annotated length; crop the file first')
    return Song(data['case_id'], data['source_style'], data['split'], tempo, bars,
                melody_track, tuple(chords), tuple(phrases), midi, path, midi_path)


def write_midi(midi: pretty_midi.PrettyMIDI, path: Path, duration_beats: int,
               phrases: tuple[Phrase, ...] = ()) -> None:
    """Retain a fixed excerpt boundary even if the last note ends before it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(path))
    raw = mido.MidiFile(path)
    # pretty_midi's writer truncates floating-point microseconds. Round constant
    # tempo explicitly so a save/reload cycle cannot lose one microsecond/beat.
    _, tempi = midi.get_tempo_changes()
    if len(tempi) == 1:
        encoded_tempo = mido.bpm2tempo(float(tempi[0]))
        for track in raw.tracks:
            for message in track:
                if message.type == 'set_tempo':
                    message.tempo = encoded_tempo
    end_tick = int(round(duration_beats * raw.ticks_per_beat))
    if phrases:
        absolute, cursor = [], 0
        for msg in raw.tracks[0]:
            cursor += msg.time
            if msg.type not in ('end_of_track', 'marker'):
                absolute.append((cursor, msg))
        absolute.extend((p.start_bar*4*raw.ticks_per_beat,
                         mido.MetaMessage('marker', text=p.label)) for p in phrases)
        absolute.sort(key=lambda item: item[0])
        raw.tracks[0][:] = []
        cursor = 0
        for tick, msg in absolute:
            raw.tracks[0].append(msg.copy(time=tick-cursor))
            cursor = tick
    for track in raw.tracks:
        total = sum(msg.time for msg in track if msg.type != 'end_of_track')
        if total > end_tick:
            raise ValueError('Output event extends beyond the excerpt boundary')
        track[:] = [msg for msg in track if msg.type != 'end_of_track']
        track.append(mido.MetaMessage('end_of_track', time=end_tick - total))
    raw.save(path)


def protected_output(song: Song) -> pretty_midi.PrettyMIDI:
    output = pretty_midi.PrettyMIDI(initial_tempo=song.tempo, resolution=song.midi.resolution)
    output.time_signature_changes = [pretty_midi.TimeSignature(4, 4, 0)]
    output.key_signature_changes = copy.deepcopy(song.midi.key_signature_changes)
    output.instruments.append(copy.deepcopy(song.melody))
    return output
