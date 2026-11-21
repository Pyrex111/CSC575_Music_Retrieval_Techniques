"""Negative controls for team integration, event preservation and split handling."""
import csv
import json

import mido
import pretty_midi
import pytest

from workstreams.taimoor.fixtures import make_fixtures
from workstreams.taimoor.independent_audit import audit_case, parse, selected_track
from workstreams.taimoor.model import load_song, write_midi
from workstreams.taimoor.run import main as run_main
from workstreams.taimoor.team_handoff import (
    SMIT_REVISION, checked_records, composition_key, inside, normalize_endpoints,
    prior_exposure, semantic_events, sha, split_conflicts, training_records,
    write_style_manifest,
)


def test_end_metadata_repair_preserves_every_other_absolute_event(tmp_path):
    source, target = tmp_path/'source.mid', tmp_path/'normalized.mid'
    raw = mido.MidiFile(ticks_per_beat=120)
    raw.tracks = [mido.MidiTrack([
        mido.MetaMessage('set_tempo', tempo=500000),
        mido.MetaMessage('end_of_track', time=1920),
    ]), mido.MidiTrack([
        mido.Message('program_change', program=73),
        mido.Message('control_change', control=1, value=30),
        mido.Message('pitchwheel', pitch=400),
        mido.Message('note_on', note=72, velocity=90),
        mido.Message('note_off', note=72, time=1920),
        mido.MetaMessage('end_of_track', time=1),
    ])]
    raw.save(source)
    original_sha = sha(source)
    changes = normalize_endpoints(source, target, 4)
    assert changes == [{'track': 1, 'original_end_tick': 1921, 'normalized_end_tick': 1920}]
    assert sha(source) == original_sha
    assert semantic_events(mido.MidiFile(source)) == semantic_events(mido.MidiFile(target))
    assert mido.MidiFile(target).length == 8


@pytest.mark.parametrize('event', [mido.Message('note_off', note=72, time=1921),
                                  mido.Message('control_change', control=1, value=0, time=1921)])
def test_late_musical_or_control_event_is_never_trimmed(tmp_path, event):
    raw = mido.MidiFile(ticks_per_beat=120)
    raw.tracks = [mido.MidiTrack([mido.Message('note_on', note=72), event])]
    path = tmp_path/'source.mid'; raw.save(path)
    with pytest.raises(ValueError, match='refusing to trim'):
        normalize_endpoints(path, tmp_path/'out.mid', 4)
    assert not (tmp_path/'out.mid').exists()


def test_large_endpoint_error_is_not_silently_repaired(tmp_path):
    raw = mido.MidiFile(ticks_per_beat=120)
    raw.tracks = [mido.MidiTrack([mido.MetaMessage('end_of_track', time=1922)])]
    path = tmp_path/'source.mid'; raw.save(path)
    with pytest.raises(ValueError, match='one-tick'):
        normalize_endpoints(path, tmp_path/'out.mid', 4)


def test_unnamed_nonfirst_melody_is_audited_and_corruption_is_rejected(tmp_path):
    annotation = make_fixtures(tmp_path/'fixtures')[0]
    info = json.loads(annotation.read_text())
    path = annotation.parent/info['midi_path']
    midi = pretty_midi.PrettyMIDI(str(path))
    midi.instruments[0], midi.instruments[2] = midi.instruments[2], midi.instruments[0]
    for instrument in midi.instruments:
        instrument.name = ''
    write_midi(midi, path, 64)
    info['melody_track'] = 2
    annotation.write_text(json.dumps(info))
    root = tmp_path/'results'
    run_main(['--annotation', str(annotation), '--output', str(root)])
    rows = audit_case(annotation, root)
    assert len(rows) == 4 and all(r['technical_pass'] for r in rows)
    corrupt_path = root/info['case_id']/'adaptive.mid'
    changed = pretty_midi.PrettyMIDI(str(corrupt_path))
    changed.instruments[0].notes[0].pitch += 1
    write_midi(changed, corrupt_path, 64, load_song(annotation).phrases)
    bad = next(r for r in audit_case(annotation, root) if r['method'] == 'adaptive')
    assert bad['melody_event_differences'] > 0 and not bad['technical_pass']


def test_raw_track_mapping_rejects_ambiguous_multiple_channels(tmp_path):
    raw = mido.MidiFile()
    raw.tracks = [mido.MidiTrack([
        mido.Message('note_on', channel=0, note=72),
        mido.Message('note_on', channel=1, note=60),
        mido.Message('note_off', channel=0, note=72, time=120),
        mido.Message('note_off', channel=1, note=60),
    ])]
    path = tmp_path/'mixed.mid'; raw.save(path)
    with pytest.raises(ValueError, match='one channel/program'):
        selected_track(parse(path), 0)


def test_split_audit_catches_resaved_and_named_variants():
    assert composition_key('What_a_Wonderful_World.1') == composition_key('what a wonderful world')
    rows = [dict(case_id='a', split='train', composition_key='same', source_sha256='x',
                 prepared_sha256='p', melody_signature_sha256='m'),
            dict(case_id='b', split='test', composition_key='same', source_sha256='y',
                 prepared_sha256='q', melody_signature_sha256='n')]
    assert split_conflicts(rows)[0]['grouped_by'] == 'composition_key'
    rows[1]['composition_key'] = 'other'
    rows[1]['source_sha256'] = 'x'
    assert split_conflicts(rows)[0]['grouped_by'] == 'source_sha256'


def test_prior_exposure_is_recorded_even_if_split_names_have_changed():
    pilot = {'cases': [{'case_id': 'old', 'composition_id': 'Song',
                        'source_git_blob': 'abc', 'split': 'development'}]}
    matches = prior_exposure({'source_id': 'Song.1'}, 'new_blob', pilot)
    assert matches == [{'prior_case_id': 'old', 'prior_split': 'development',
                        'match': 'normalized_composition_name'}]


def test_training_selection_does_not_require_validation_or_test_inputs():
    records = [dict(case_id='a', split='train', source_style='jazz'),
               dict(case_id='b', split='train', source_style='rock'),
               dict(case_id='unopenable', split='val'), dict(case_id='unopenable2', split='test')]
    assert [r['case_id'] for r in training_records(records)] == ['a', 'b']


def test_style_adapter_uses_excerpt_melody_index_and_validation_spelling(tmp_path):
    row = dict(midi='prepared/a.mid', composition_key='song', source_style='jazz',
               split='val', melody_track=3, case_id='a')
    write_style_manifest(tmp_path, [row])
    result = next(csv.DictReader((tmp_path/'style_dataset.csv').open()))
    assert result['melody_track_index'] == '3' and result['split'] == 'validation'
    assert result['composition_id'] == 'song'


def test_changed_prepared_midi_stops_smoke_before_arrangement(tmp_path):
    midi, annotation, manifest = tmp_path/'a.mid', tmp_path/'a.json', tmp_path/'style_dataset.csv'
    midi.write_bytes(b'original'); annotation.write_text('{}'); manifest.write_text('example')
    report = {'source_revision': SMIT_REVISION, 'failures': [], 'cross_split_conflicts': [],
              'style_manifest_sha256': sha(manifest),
              'records': [dict(midi='a.mid', annotation='a.json', prepared_sha256=sha(midi),
                               annotation_sha256=sha(annotation))]}
    (tmp_path/'handoff_audit.json').write_text(json.dumps(report))
    assert len(checked_records(tmp_path)) == 1
    midi.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='changed'):
        checked_records(tmp_path)


def test_input_path_escape_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='escapes'):
        inside(tmp_path, '../outside.mid')
