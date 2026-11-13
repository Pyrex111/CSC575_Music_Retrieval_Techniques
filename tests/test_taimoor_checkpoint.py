"""Regression checks for source-derived input handling and fair baseline checks."""
import json

import pretty_midi
import pytest

from workstreams.taimoor.arranger import arrange
from workstreams.taimoor.checkpoint import crop_midi, references, valid
from workstreams.taimoor.fixtures import make_fixtures
from workstreams.taimoor.evaluate import measure
from workstreams.taimoor.independent_audit import audit_case
from workstreams.taimoor.model import load_song, write_midi
from workstreams.taimoor.run import main as run_main


def test_gm_bass_without_track_name_remains_a_bass_palette(tmp_path):
    song = load_song(make_fixtures(tmp_path/'fixtures')[0])
    song.midi.instruments[1].name = ''
    song.midi.instruments[1].program = 34
    output, _ = arrange(song, 'jazz', 'instrument_only')
    assert output.instruments[1].program == 32


def test_baseline_nonchord_tone_does_not_hide_a_generated_failure(tmp_path):
    annotation = make_fixtures(tmp_path/'fixtures')[0]
    info = json.loads(annotation.read_text())
    source = annotation.parent/info['midi_path']
    midi = pretty_midi.PrettyMIDI(str(source))
    midi.instruments[1].notes[0].pitch = 25  # Retained nonchord tone, outside generator register.
    write_midi(midi, source, 64)
    output = tmp_path/'results'
    run_main(['--annotation',str(annotation),'--output',str(output)])
    report = json.loads((output/'results.json').read_text())
    baseline = next(r for r in report['runs'] if r['method']=='instrument_only')
    assert baseline['metrics']['harmony_pitch_class_violations'] > 0
    assert valid(baseline['metrics'],'instrument_only')
    assert not valid(baseline['metrics'],'adaptive')
    assert all(r['metrics']['harmony_pitch_class_violations']==0 for r in report['runs'] if r['method']!='instrument_only')
    # The independent raw audit uses the same applicability distinction, retaining all melody checks.
    rows = audit_case(annotation, output)
    assert all(r['technical_pass'] for r in rows)
    adaptive_path = output/info['case_id']/'adaptive.mid'
    corrupt = pretty_midi.PrettyMIDI(str(adaptive_path))
    corrupt.instruments[0].notes[0].pitch += 1
    write_midi(corrupt,adaptive_path,64,load_song(annotation).phrases)
    changed = next(r for r in audit_case(annotation,output) if r['method']=='adaptive')
    assert not changed['technical_pass']
    assert changed['melody_event_differences'] > 0


def test_crop_reports_boundary_edits_and_carries_expression():
    midi=pretty_midi.PrettyMIDI(initial_tempo=120)
    track=pretty_midi.Instrument(73)
    track.notes=[pretty_midi.Note(95,72,7.5,8.5),pretty_midi.Note(80,74,9,10)]
    track.control_changes=[pretty_midi.ControlChange(1,22,1),pretty_midi.ControlChange(1,40,9)]
    track.pitch_bends=[pretty_midi.PitchBend(250,1)]
    midi.instruments=[track]
    crop,index,trimmed=crop_midi(midi,120,4,4,0)
    assert trimmed==1 and index==0
    assert crop.instruments[0].notes[0].start==0
    assert crop.instruments[0].notes[0].end==pytest.approx(0.5)
    assert [(x.value,x.time) for x in crop.instruments[0].control_changes]==[(22,0),(40,1)]
    assert crop.instruments[0].pitch_bends[0].pitch==250


def test_reference_profiles_never_open_held_out_annotations(tmp_path):
    from types import SimpleNamespace
    paths=make_fixtures(tmp_path/'fixtures')
    records=[{'split':'development','case_id':str(i),'annotation':str(path.relative_to(tmp_path))}
             for i,path in enumerate(paths[:2])]
    # A held-out path that cannot be read must not affect reference fitting.
    records.append({'split':'test','case_id':'heldout','annotation':'must_not_be_opened.json'})
    module=SimpleNamespace(extract_style_features=lambda midi,mi: {
        'note_density':1.0,'average_polyphony':2.0,'offbeat_activity':0.3,'average_note_duration':0.25})
    result=references(tmp_path,records,module)
    assert result['reference_cases']==['0','1']
    assert set(result['centers'])=={'jazz','rock'}


@pytest.mark.parametrize('tempo',[90.000900009,98.0001437335,126.0001260001])
def test_encoded_midi_tempo_controls_bar_assignment_and_duration(tmp_path,tempo):
    annotation=make_fixtures(tmp_path/'fixtures')[0]
    data=json.loads(annotation.read_text()); source=annotation.parent/data['midi_path']
    midi=pretty_midi.PrettyMIDI(str(source))
    scaled=pretty_midi.PrettyMIDI(initial_tempo=tempo,resolution=midi.resolution)
    scaled.time_signature_changes=[pretty_midi.TimeSignature(4,4,0)]
    scaled.instruments=midi.instruments
    for instrument in scaled.instruments:
        for note in instrument.notes:
            note.start*=120/tempo;note.end*=120/tempo
    write_midi(scaled,source,64)
    data['tempo_bpm']=tempo;annotation.write_text(json.dumps(data))
    song=load_song(annotation)
    root=tmp_path/'out'
    for method in ['instrument_only','fixed','adaptive','no_continuity']:
        output,trace=arrange(song,'jazz',method)
        path=root/song.case_id/f'{method}.mid'
        write_midi(output,path,64,song.phrases)
        metrics,_=measure(song,path,trace['melody_track'])
        assert valid(metrics,method),metrics
    assert all(r['technical_pass'] for r in audit_case(annotation,root))
