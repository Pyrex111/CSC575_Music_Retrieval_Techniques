"""Hand-authored candidates + exact dynamic programming with repeat constraints.

Descriptor profiles/weights are engineering defaults, not learned genre models.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import copy
import math

import pretty_midi

from .model import Chord, Phrase, Song, protected_output


PALETTES = {'rock': (33, 27), 'jazz': (32, 0)}  # zero-based GM bass/chords
RANGES = {'bass': (36, 60), 'chords': (48, 84)}


@dataclass(frozen=True)
class Weights:
    style: float = 1.0
    continuity: float = 0.8
    max_states: int = 100000

    def __post_init__(self):
        if any(not math.isfinite(x) or x < 0 for x in (self.style, self.continuity)):
            raise ValueError('Weights must be finite and nonnegative')
        if type(self.max_states) is not int or self.max_states < 1:
            raise ValueError('max_states must be a positive integer')


@dataclass(frozen=True)
class Event:
    role: str
    pitch: int
    start: float
    duration: float
    velocity: int


@dataclass(frozen=True)
class Pattern:
    name: str
    bass: tuple[tuple[float, int], ...]
    comp: tuple[float, ...]
    drums: tuple[tuple[float, int], ...]


def patterns(style: str) -> tuple[Pattern, ...]:
    if style not in PALETTES:
        raise ValueError('target_style must be jazz or rock')
    if style == 'rock':
        hats = tuple((i / 2, 42) for i in range(8))
        drums = hats + ((0, 36), (2, 36), (1, 38), (3, 38))
        return (
            Pattern('sparse', ((0, 0), (2, 0)), (0,), drums[::2]),
            Pattern('regular', ((0, 0), (1, 0), (2, 2), (3, 0)), (0, 2), drums),
            Pattern('busy', tuple((i / 2, i % 3) for i in range(8)), (0, 1.5, 2, 3.5),
                    drums + ((2.5, 36), (3.5, 38))),
        )
    ride = ((0, 51), (1, 51), (5/3, 51), (2, 51), (3, 51), (11/3, 51))
    drums = ride + ((1, 44), (3, 44), (0, 36))
    return (
        Pattern('sparse', ((0, 0), (2, 2)), (2/3,), ride[::2]),
        Pattern('regular', ((0, 0), (1, 1), (2, 2), (3, 1)), (2/3, 8/3), drums),
        Pattern('busy', ((0, 0), (2/3, 1), (1, 2), (2, 0), (8/3, 2), (3, 1)),
                (2/3, 5/3, 8/3, 11/3), drums + ((5/3, 38), (11/3, 38))),
    )


def tone(pc: int, register: tuple[int, int], preferred: int) -> int:
    choices = [p for p in range(register[0], register[1] + 1) if p % 12 == pc % 12]
    if not choices:
        raise ValueError('No chord tone within instrument register')
    return min(choices, key=lambda p: (abs(p - preferred), p))


def adapt(pattern: Pattern, chord: Chord, bar: int) -> tuple[Event, ...]:
    """Map template indices to chord tones; do not reharmonize the chord map."""
    events = []
    for beat, degree in pattern.bass:
        pitch = tone(chord.root_pc + chord.intervals[degree % len(chord.intervals)],
                     RANGES['bass'], 43)
        events.append(Event('bass', pitch, bar*4 + beat, min(0.8, 4-beat), 82))
    for beat in pattern.comp:
        for degree, interval in enumerate(chord.intervals):
            pitch = tone(chord.root_pc + interval, RANGES['chords'], 58 + 4*degree)
            events.append(Event('chords', pitch, bar*4 + beat, min(0.45, 4-beat), 64))
    for beat, pitch in pattern.drums:
        events.append(Event('drums', pitch, bar*4 + beat, min(0.12, 4-beat), 65))
    return tuple(events)


def plan_names(phrase: Phrase, name: str) -> tuple[str, ...]:
    if name in ('sparse', 'regular', 'busy'):
        return (name,) * phrase.bars
    levels = ('sparse', 'regular', 'busy') if name == 'build' else ('busy', 'regular', 'sparse')
    return tuple(levels[min(2, int(i * 3 / phrase.bars))] for i in range(phrase.bars))


def density(song: Song, bar: int) -> float:
    spb = song.seconds_per_beat
    return sum(bar*4 <= n.start/spb < (bar+1)*4 for n in song.melody.notes) / 4


def local_cost(song: Song, phrase: Phrase, names: tuple[str, ...], bank: dict,
               style: str) -> float:
    """Explicit, hand-designed context profile; smaller cost is preferred.

    Sparse melody -> more accompaniment attacks; dense melody -> fewer attacks.
    The offbeat term encodes a limited preset distinction, not a learned genre.
    """
    total = 0.0
    for index, name in enumerate(names):
        pattern = bank[name]
        melodic_density = density(song, phrase.start_bar + index)
        desired_bass = max(1.5, 6 - 2*melodic_density)
        desired_comp = max(1.0, 4 - melodic_density)
        offbeat = sum(abs(t-round(t)) > 1e-6 for t in pattern.comp) / len(pattern.comp)
        desired_offbeat = 1.0 if style == 'jazz' else 0.25
        total += ((len(pattern.bass)-desired_bass)/4)**2
        total += ((len(pattern.comp)-desired_comp)/2)**2
        total += 0.25 * (offbeat-desired_offbeat)**2
    return total


@dataclass(frozen=True)
class Candidate:
    plan: str
    names: tuple[str, ...]
    events: tuple[Event, ...]
    local: float


def candidates(song: Song, phrase: Phrase, style: str) -> tuple[Candidate, ...]:
    bank = {p.name: p for p in patterns(style)}
    result = []
    for plan in ('sparse', 'regular', 'busy', 'build', 'release'):
        names = plan_names(phrase, plan)
        events = tuple(e for i, name in enumerate(names)
                       for e in adapt(bank[name], song.chords[phrase.start_bar+i], phrase.start_bar+i))
        result.append(Candidate(plan, names, events, local_cost(song, phrase, names, bank, style)))
    return tuple(result)


def transition(previous: Candidate, current: Candidate) -> float:
    prev_bass = [e for e in previous.events if e.role == 'bass']
    next_bass = [e for e in current.events if e.role == 'bass']
    last = max(prev_bass, key=lambda e: e.start)
    first = min(next_bass, key=lambda e: e.start)
    # Texture change uses attacks per bar so unequal phrase lengths are comparable.
    density_jump = abs(len(previous.events)/len(previous.names) -
                       len(current.events)/len(current.names)) / 24
    return abs(last.pitch-first.pitch)/12 + density_jump


def select(song: Song, style: str, weights: Weights = Weights(),
           fixed: bool = False) -> tuple[tuple[Candidate, ...], float]:
    banks = [candidates(song, phrase, style) for phrase in song.phrases]
    if fixed:
        path = tuple(next(c for c in bank if c.plan == 'regular') for bank in banks)
        score = weights.style*sum(c.local for c in path)
        score += weights.continuity*sum(transition(a, b) for a, b in zip(path, path[1:]))
        return path, score
    counts = Counter(p.label for p in song.phrases)
    last_occurrence = {p.label: i for i, p in enumerate(song.phrases)}
    # State=(last candidate index, live repeated-label assignments).
    # Dropping assignments after their final use keeps the search compact.
    states = {(-1, ()): (0.0, ())}
    for index, (phrase, bank) in enumerate(zip(song.phrases, banks)):
        updated = {}
        for (_, assignments), (score, path) in states.items():
            assigned = dict(assignments)
            for candidate_index, candidate in enumerate(bank):
                if phrase.label in assigned and assigned[phrase.label] != candidate.plan:
                    continue
                kept = dict(assigned)
                if counts[phrase.label] > 1:
                    kept[phrase.label] = candidate.plan
                kept = {label: plan for label, plan in kept.items() if last_occurrence[label] > index}
                cost = score + weights.style*candidate.local
                if path:
                    cost += weights.continuity*transition(path[-1], candidate)
                key = (candidate_index, tuple(sorted(kept.items())))
                if key not in updated or cost < updated[key][0]:
                    updated[key] = (cost, path + (candidate,))
        if len(updated) > weights.max_states:
            raise ValueError('Selection state limit exceeded; reduce repeated phrase labels/candidates')
        states = updated
    best_score, best_path = min(states.values(), key=lambda item: item[0])
    return best_path, best_score


def arrange(song: Song, target_style: str, method: str = 'adaptive',
            weights: Weights = Weights()):
    if target_style not in PALETTES:
        raise ValueError('target_style must be jazz or rock')
    if method not in ('instrument_only', 'fixed', 'adaptive', 'no_continuity'):
        raise ValueError('Unknown method')
    if method == 'instrument_only':
        result = copy.deepcopy(song.midi)
        for index, instrument in enumerate(result.instruments):
            if index != song.melody_track and not instrument.is_drum:
                bass = 'bass' in instrument.name.lower() or 32 <= instrument.program <= 39
                instrument.program = PALETTES[target_style][0 if bass else 1]
        return result, {'method': method, 'melody_track': song.melody_track, 'selection': [],
                        'weights': asdict(weights), 'selection_objective': None}
    effective = Weights(weights.style, 0 if method == 'no_continuity' else weights.continuity,
                        weights.max_states)
    selected, objective = select(song, target_style, effective, fixed=method == 'fixed')
    result = protected_output(song)
    tracks = {
        'bass': pretty_midi.Instrument(PALETTES[target_style][0], name='bass'),
        'chords': pretty_midi.Instrument(PALETTES[target_style][1], name='chords'),
        'drums': pretty_midi.Instrument(0, is_drum=True, name='drums'),
    }
    for candidate in selected:
        for event in candidate.events:
            if event.start < 0 or event.duration <= 0 or event.start+event.duration > song.duration_beats:
                raise ValueError('Invalid generated event timing')
            if not 0 <= event.pitch <= 127:
                raise ValueError('Invalid generated MIDI pitch')
            tracks[event.role].notes.append(pretty_midi.Note(
                event.velocity, event.pitch, event.start*song.seconds_per_beat,
                (event.start+event.duration)*song.seconds_per_beat))
    result.instruments.extend(tracks.values())
    return result, {
        'method': method, 'melody_track': 0, 'weights': asdict(effective),
        'selection_objective': objective,
        'selection': [{'phrase': p.label, 'start_bar': p.start_bar, 'bars': p.bars,
                       'plan': c.plan, 'patterns': list(c.names), 'local_cost': c.local,
                       'transition_from_previous': transition(selected[i-1], c) if i else 0}
                      for i, (p, c) in enumerate(zip(song.phrases, selected))],
    }
