"""Selection oracle, preservation controls and development-data boundary tests."""
import itertools
import json
import csv
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pretty_midi
import pytest

pytest.importorskip('pandas')
pytest.importorskip('sklearn')

from workstreams.taimoor.advanced_study import development_roles, summarize_grid, validated_run, verify_training_inputs
from workstreams.taimoor.arranger import Weights, arrange, candidates, select, transition
from workstreams.taimoor.fixtures import make_fixtures
from workstreams.taimoor.independent_audit import audit_case
from workstreams.taimoor.learned_ranking import LearnedPenalty, anchored_features, candidate_midi
from workstreams.taimoor.model import Phrase, load_song, write_midi
from workstreams.taimoor.split_proposal import REVIEW_FIELDS, candidate_splits, propose, readiness
from workstreams.taimoor.team_handoff import dump, sha


def test_external_cost_dp_matches_exhaustive_repeated_phrase_oracle(tmp_path):
    song = load_song(make_fixtures(tmp_path/'fixtures')[0])
    penalty = lambda song, phrase, candidate, style: float((phrase.start_bar+len(candidate.plan)) % 5)
    weights = Weights(1, .75)
    result, score = select(song, 'jazz', weights, candidate_scorer=penalty)
    banks = [candidates(song, p, 'jazz', penalty) for p in song.phrases]
    totals = []
    for path in itertools.product(*banks):
        labels = {}
        consistent = True
        for phrase, candidate in zip(song.phrases, path):
            if phrase.label in labels and labels[phrase.label] != candidate.plan:
                consistent = False
            labels[phrase.label] = candidate.plan
        if not consistent:
            continue
        totals.append(sum(c.local for c in path)+.75*sum(transition(a,b) for a,b in zip(path,path[1:])))
    assert score == pytest.approx(min(totals))
    assert result[0].plan == result[2].plan


def test_learned_preference_changes_plans_without_changing_melody(tmp_path):
    annotation = make_fixtures(tmp_path/'fixtures')[0]
    song = load_song(annotation)
    penalty = lambda song, phrase, candidate, style: 0 if candidate.plan == 'sparse' else 10000
    midi, trace = arrange(song, 'jazz', weights=Weights(1,0), candidate_scorer=penalty)
    assert {p['plan'] for p in trace['selection']} == {'sparse'}
    assert all(p['local_cost'] == p['heuristic_local_cost']+p['reranker_penalty'] for p in trace['selection'])
    path = tmp_path/'outputs'/song.case_id/'learned.mid'
    write_midi(midi, path, song.duration_beats, song.phrases)
    row = audit_case(annotation, tmp_path/'outputs', methods=('learned',))[0]
    assert row['technical_pass'] and row['melody_event_differences'] == 0


def test_zero_weight_does_not_call_model_and_preserves_heuristic_bytes(tmp_path):
    song = load_song(make_fixtures(tmp_path/'fixtures')[0])
    base, _ = arrange(song, 'jazz', weights=Weights(1,4))
    zero, _ = arrange(song, 'jazz', weights=Weights(1,4), candidate_scorer=LearnedPenalty(None,None,0))
    a,b = tmp_path/'a.mid', tmp_path/'b.mid'
    write_midi(base,a,song.duration_beats,song.phrases);write_midi(zero,b,song.duration_beats,song.phrases)
    assert a.read_bytes() == b.read_bytes()


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1])
def test_invalid_external_cost_is_rejected(tmp_path,value):
    song = load_song(make_fixtures(tmp_path/'fixtures')[0])
    with pytest.raises(ValueError,match='finite and nonnegative'):
        arrange(song,'jazz',candidate_scorer=lambda *args:value)


@pytest.mark.parametrize('method',['fixed','instrument_only'])
def test_baseline_cannot_accidentally_receive_a_learned_score(tmp_path,method):
    song = load_song(make_fixtures(tmp_path/'fixtures')[0])
    with pytest.raises(ValueError,match='comparators'):
        arrange(song,'jazz',method,candidate_scorer=lambda *args:0)


def test_descriptor_duration_anchor_is_explicit_and_does_not_mutate_input():
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    instrument = pretty_midi.Instrument(0);instrument.notes=[pretty_midi.Note(90,60,0,1)]
    midi.instruments=[instrument]
    seen=[]
    team=SimpleNamespace(features=SimpleNamespace(extract_style_features=lambda m,i: seen.append(m.get_end_time()) or {'x':1}),
                         classifier=SimpleNamespace(FEATURE_NAMES=['x']))
    assert anchored_features(team,midi,0,8) == {'x':1}
    assert seen == [8] and midi.get_end_time() == 1 and not midi.text_events


def test_nonprobability_learned_score_is_rejected(tmp_path):
    song=load_song(make_fixtures(tmp_path/'fixtures')[0]);phrase=song.phrases[0]
    team=SimpleNamespace(features=SimpleNamespace(extract_style_features=lambda m,i:{'x':1}),
                         classifier=SimpleNamespace(FEATURE_NAMES=['x']),
                         ranking=SimpleNamespace(calculate_style_score=lambda *args:1.1))
    with pytest.raises(ValueError,match='probability'):
        LearnedPenalty(team,None,1)(song,phrase,candidates(song,phrase,'jazz')[0],'jazz')


def test_late_phrase_view_tolerates_only_float_roundoff(tmp_path):
    song=load_song(make_fixtures(tmp_path/'fixtures')[0])
    song=replace(song,bars=32,chords=song.chords*2)
    phrase=Phrase('late',20,4)
    candidate=next(c for c in candidates(song,phrase,'jazz') if c.plan=='busy')
    midi=candidate_midi(song,phrase,candidate,'jazz')
    assert midi.get_end_time() <= phrase.bars*4*song.seconds_per_beat
    bad=replace(candidate,events=(replace(candidate.events[0],start=96.1),))
    with pytest.raises(ValueError,match='outside the phrase'):
        candidate_midi(song,phrase,bad,'jazz')


def test_internal_development_roles_never_select_original_validation_or_test():
    rows=[dict(case_id=f'{g}{i}',composition_key=f'{g}{i}',source_style=g,split='train')
          for g in ['jazz','rock'] for i in range(8)]
    rows += [dict(case_id='unopenable',split='test'),dict(case_id='also_unopenable',split='val')]
    fit,check=development_roles(rows,checks_per_genre=2)
    assert len(fit)==12 and len(check)==4
    assert not {r['composition_key'] for r in fit}&{r['composition_key'] for r in check}
    assert all(r['split']=='train' for r in fit+check)


def test_validation_record_is_rejected_before_any_file_open(tmp_path):
    with pytest.raises(ValueError,match='refuses original validation/test'):
        verify_training_inputs(tmp_path,[{'split':'test'}])


def test_incomplete_grid_does_not_become_eligible_by_dropping_failure():
    row={'technical_pass':True,'raw_audit':{'technical_pass':True},'selection_proxy':.5}
    assert not summarize_grid([row],2)['eligible']
    assert summarize_grid([row],2)['mean_selection_proxy'] is None


def test_code_change_blocks_model_load_before_deserialization(tmp_path,monkeypatch):
    dump(tmp_path/'model_manifest.json',{'code_sha256':{},'handoff_audit_sha256':'x'})
    import workstreams.taimoor.advanced_study as study
    monkeypatch.setattr(study.joblib,'load',lambda p:pytest.fail('Must not deserialize after code drift'))
    with pytest.raises(ValueError,match='changed after model fitting'):
        validated_run(tmp_path,tmp_path,tmp_path)


def r(case,genre,split,key=None,exposed=False):
    return dict(case_id=case,composition_key=key or case,composition_id=key or case,source_style=genre,
                split=split,prior_pilot_matches=[{}] if exposed else [],annotation_sha256='abc')


def test_proposed_test_excludes_pilot_training_and_duplicate_versions():
    records=[r('jtrain','jazz','train','same'),r('jduplicate','jazz','val','same'),
             r('rtrain','rock','train'),r('joldtest','jazz','test',exposed=True),
             r('roldtest','rock','test',exposed=True),r('jfresh','jazz','val'),r('rfresh','rock','val')]
    rows,excluded,shortage,protected=candidate_splits(records,per_genre_test=1)
    assert {r['case_id'] for r in rows if r['proposed_split']=='test'}=={'jfresh','rfresh'}
    assert excluded[0]['case_id']=='jduplicate' and shortage=={'jazz':0,'rock':0}
    assert all(r['composition_key'] not in protected for r in rows if r['proposed_split']=='test')


def test_shortage_is_reported_instead_of_reusing_an_exposed_test():
    rows,_,shortage,_=candidate_splits([r('j','jazz','test',exposed=True),r('r','rock','train')],1)
    assert shortage=={'jazz':1,'rock':1}
    assert not any(r['proposed_split']=='test' for r in rows)


def test_proposed_manifest_paths_resolve_from_the_csv_location(tmp_path):
    handoff=tmp_path/'handoff';handoff.mkdir();(handoff/'prepared').mkdir()
    rows=[]
    for genre in ['jazz','rock']:
        path=handoff/'prepared'/(genre+'.mid');path.write_bytes(b'fixture path only')
        rows.append({**r(genre,genre,'train'),'midi':'prepared/'+path.name,'melody_track':0})
    dump(handoff/'handoff_audit.json',{'records':rows,'failures':[],'planned_compositions':2})
    output=tmp_path/'proposal';propose(handoff,output)
    for row in csv.DictReader((output/'proposed_manifest.csv').open()):
        assert (output/row['midi_path']).resolve()==(handoff/'prepared'/(row['case_id']+'.mid')).resolve()


def test_filling_reviews_cannot_bypass_missing_compositions_or_team_agreement(tmp_path):
    row={**r('one','jazz','train'),'proposed_split':'train'}
    dump(tmp_path/'split_proposal.json',{'rows':[row],'protected_from_test_composition_keys':['one']})
    fields=['case_id','annotation_sha256',*REVIEW_FIELDS,'reviewer','review_note']
    values=['one','abc',*['true']*len(REVIEW_FIELDS),'real reviewer','Recorded review']
    (tmp_path/'annotation_review.csv').write_text(','.join(fields)+'\n'+','.join(values)+'\n')
    report=readiness(tmp_path)
    assert report['checks']['reviews_complete_and_hash_bound']
    assert not report['checks']['team_agreement_recorded']
    assert not report['final_evaluation_ready']
