"""Behavioural checks, including an independent brute-force optimization oracle."""
import itertools
import json

import mido
import pretty_midi
import pytest

from workstreams.taimoor.arranger import (
    RANGES, Weights, adapt, arrange, candidates, patterns, select, transition,
)
from workstreams.taimoor.evaluate import measure
from workstreams.taimoor.fixtures import make_fixtures
from workstreams.taimoor.model import Chord, load_song, write_midi
from workstreams.taimoor.run import main


@pytest.fixture
def annotations(tmp_path):
    return make_fixtures(tmp_path/'fixtures')


@pytest.mark.parametrize('case_index', range(4))
@pytest.mark.parametrize('method', ['instrument_only', 'fixed', 'adaptive', 'no_continuity'])
def test_exported_midi_preserves_protected_content(annotations, tmp_path, case_index, method):
    song = load_song(annotations[case_index])
    target = 'jazz' if song.source_style == 'rock' else 'rock'
    midi, trace = arrange(song, target, method)
    output = tmp_path/f'{case_index}_{method}.mid'
    write_midi(midi, output, song.duration_beats, song.phrases)
    metrics, _ = measure(song, output, trace['melody_track'])
    for name in ['melody_preserved', 'duration_preserved', 'phrase_markers_preserved',
                 'tempo_preserved', 'time_signature_preserved']:
        assert metrics[name], (name, metrics)
    for name in ['harmony_pitch_class_violations', 'register_violations', 'event_bounds_violations']:
        assert metrics[name] == 0
    assert metrics['duration_seconds'] == pytest.approx(32 if case_index < 2 else 48)


@pytest.mark.parametrize('style', ['jazz', 'rock'])
@pytest.mark.parametrize('intervals', [(0, 4, 7), (0, 3, 7), (0, 4, 7, 10)])
def test_every_root_and_template_maps_to_chord_and_register(style, intervals):
    for root in range(12):
        chord = Chord(root, intervals)
        for pattern in patterns(style):
            for note in adapt(pattern, chord, 0):
                assert note.duration > 0 and 0 <= note.start < note.start+note.duration <= 4
                if note.role != 'drums':
                    assert (note.pitch-root) % 12 in intervals
                    assert RANGES[note.role][0] <= note.pitch <= RANGES[note.role][1]


def test_dynamic_program_matches_exhaustive_search_with_repeated_phrases(annotations):
    song = load_song(annotations[0])
    weights = Weights(style=1, continuity=2.1)
    selected, score = select(song, 'jazz', weights)
    banks = [candidates(song, p, 'jazz') for p in song.phrases]
    possibilities = []
    for path in itertools.product(*banks):
        if path[0].plan != path[2].plan:  # A/B/A/C fixture, enforced independently.
            continue
        cost = sum(c.local for c in path) + weights.continuity*sum(
            transition(a, b) for a, b in zip(path, path[1:]))
        possibilities.append(cost)
    assert score == pytest.approx(min(possibilities))
    assert selected[0].names == selected[2].names


def test_continuity_weight_can_change_decision(annotations):
    song = load_song(annotations[0])
    local, _ = select(song, 'jazz', Weights(1, 0))
    smooth, _ = select(song, 'jazz', Weights(1, 100))
    local_transitions = sum(transition(a, b) for a, b in zip(local, local[1:]))
    smooth_transitions = sum(transition(a, b) for a, b in zip(smooth, smooth[1:]))
    assert smooth_transitions < local_transitions
    assert [x.plan for x in local] != [x.plan for x in smooth]


def test_arranging_does_not_mutate_source_and_repeats_deterministically(annotations):
    song = load_song(annotations[0])
    before = [(i.program, [(n.pitch, n.start, n.end) for n in i.notes]) for i in song.midi.instruments]
    _, first = arrange(song, 'jazz')
    _, second = arrange(song, 'jazz')
    assert first == second
    assert before == [(i.program, [(n.pitch, n.start, n.end) for n in i.notes]) for i in song.midi.instruments]


def test_invalid_annotations_are_rejected(annotations):
    path = annotations[0]
    original = json.loads(path.read_text())
    invalid_cases = [
        {'case_id': '../escape'},
        {'melody_track': 500}, {'melody_track': 3}, {'tempo_bpm': 0},
        {'time_signature': [3, 4]}, {'chords': original['chords'][:-1]},
        {'phrases': [{'label': 'A', 'start_bar': 1, 'bars': 16}]},
    ]
    for change in invalid_cases:
        path.write_text(json.dumps({**original, **change}))
        with pytest.raises(ValueError):
            load_song(path)


def test_tempo_changes_are_rejected(annotations):
    path = annotations[0]
    data = json.loads(path.read_text())
    midi_path = path.parent/data['midi_path']
    raw = mido.MidiFile(midi_path)
    raw.tracks[0].insert(1, mido.MetaMessage('set_tempo', tempo=600000, time=1))
    raw.save(midi_path)
    with pytest.raises(ValueError, match='tempo'):
        load_song(path)


def test_evaluation_detects_a_changed_melody_pitch(annotations, tmp_path):
    song = load_song(annotations[0])
    output, _ = arrange(song, 'jazz')
    output.instruments[0].notes[0].pitch += 1
    path = tmp_path/'bad.mid'
    write_midi(output, path, song.duration_beats, song.phrases)
    metrics, _ = measure(song, path, 0)
    assert not metrics['melody_preserved']
    assert metrics['melody_pitch_errors'] == 1


@pytest.mark.parametrize('method', ['instrument_only', 'adaptive'])
def test_selected_melody_need_not_be_first_track(annotations, tmp_path, method):
    annotation = annotations[0]
    data = json.loads(annotation.read_text())
    midi_path = annotation.parent/data['midi_path']
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    midi.instruments[0], midi.instruments[1] = midi.instruments[1], midi.instruments[0]
    write_midi(midi, midi_path, 64)
    data['melody_track'] = 1
    annotation.write_text(json.dumps(data))
    song = load_song(annotation)
    output, trace = arrange(song, 'jazz', method)
    path = tmp_path/f'nonfirst_{method}.mid'
    write_midi(output, path, song.duration_beats, song.phrases)
    metrics, _ = measure(song, path, trace['melody_track'])
    assert metrics['melody_preserved']


def test_state_limit_is_explicit_not_silent_approximation(annotations):
    song = load_song(annotations[0])
    with pytest.raises(ValueError, match='state limit'):
        select(song, 'jazz', Weights(max_states=1))


@pytest.mark.parametrize('style,continuity', [(float('nan'), 1), (-1, 1), (1, float('inf'))])
def test_invalid_weights(style, continuity):
    with pytest.raises(ValueError):
        Weights(style, continuity)


def test_runner_writes_reproducible_evidence(tmp_path):
    folder = tmp_path/'results'
    main(['--output', str(folder)])
    report = json.loads((folder/'results.json').read_text())
    assert report['evidence_type'] == 'synthetic_engineering_checks'
    assert len(report['runs']) == 16
    assert set(row['target_style'] for row in report['runs']) == {'rock', 'jazz'}
    adaptive = [row for row in report['runs'] if row['method'] == 'adaptive']
    assert all(row['accompaniment_event_difference_from_fixed'] > 0 for row in adaptive)
    assert all(len(row['output_sha256']) == 64 for row in report['runs'])
    assert (folder/'summary.md').exists()
