"""Recheck saved exports after the encoded-tempo evaluator correction.

This does not arrange, select parameters, replace the original evaluation, or
rewrite any MIDI. The first-run failures remain available for inspection.
"""
import argparse
import copy
import json
from pathlib import Path

import pretty_midi

from workstreams.taimoor.checkpoint import (boundary_metrics, code_hashes, descriptor,
    distance, dump, feature_module, sha, valid)
from workstreams.taimoor.evaluate import measure
from workstreams.taimoor.independent_audit import audit_case
from workstreams.taimoor.model import load_song


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.output.resolve()
    original=json.loads((root/'evaluation.json').read_text())
    selection=json.loads((root/'frozen_selection.json').read_text())
    preparation=json.loads((root/'preparation.json').read_text())
    plan=json.loads((root/'protocol.json').read_text())
    module=feature_module(root,plan)
    revised=copy.deepcopy(original);audits=[]
    before={row['output']:sha(root/row['output']) for row in original['runs']}
    for record in preparation['prepared']:
        song=load_song(root/record['annotation'])
        signatures={}
        for row in revised['runs']:
            if row['case_id']!=song.case_id:continue
            path=root/row['output']
            if sha(path)!=row['output_sha256']:
                raise ValueError('Saved output changed after frozen evaluation')
            metrics,signature=measure(song,path,row['trace']['melody_track'])
            signatures[row['method']]=signature
            row['metrics']=metrics;row['technical_pass']=valid(metrics,row['method'])
            midi=pretty_midi.PrettyMIDI(str(path))
            row['musical_measurements']=boundary_metrics(midi,row['trace']['melody_track'],song)
            vector=descriptor(module,midi,row['trace']['melody_track'],song.tempo)
            row['descriptor_vector']=vector.tolist()
            row['target_reference_distance']=distance(vector,row['target_style'],selection['target_references'])
        for row in [r for r in revised['runs'] if r['case_id']==song.case_id]:
            row['accompaniment_events_different_from_fixed']=sum((signatures[row['method']]-signatures['fixed']).values())+sum((signatures['fixed']-signatures[row['method']]).values())
        audits.extend(audit_case(root/record['annotation'],root/'outputs'))
    after={row['output']:sha(root/row['output']) for row in original['runs']}
    assert before==after
    revised['raw_midi_audit']=audits
    revised['measurement_code_sha256']=code_hashes()
    revised['recheck_note']='Post hoc evaluator correction on identical saved MIDI and frozen weights; not a new untouched hold-out study.'
    dump(root/'evaluation_rechecked.json',revised)
    dump(root/'repair_record.json',{
        'reason':'BPM floats diverged slightly from encoded integer MIDI tempo, misassigning some downbeat notes to the preceding chord bar; the raw audit also compared duration against the BPM approximation instead of the source file.',
        'change':'Use encoded source/output tempo for event-to-beat conversion and compare output duration directly with the source duration. Keep the original one-tick annotation agreement diagnostic.',
        'original_evaluation_sha256':sha(root/'evaluation.json'),
        'frozen_selection_sha256':sha(root/'frozen_selection.json'),
        'original_code_sha256':original['code_sha256'],
        'corrected_measurement_code_sha256':code_hashes(),
        'parameters_changed':False,'arrangements_regenerated':False,
        'all_midi_hashes_unchanged':before==after,
        'first_run_technical_passes':sum(r['technical_pass'] for r in original['runs']),
        'first_run_raw_audit_passes':sum(r['technical_pass'] for r in original['raw_midi_audit']),
        'rechecked_technical_passes':sum(r['technical_pass'] for r in revised['runs']),
        'rechecked_raw_audit_passes':sum(r['technical_pass'] for r in audits),
        'regression_tests':'Decimal-BPM regression cases at 90.000900009, 98.0001437335, and 126.0001260001 BPM, plus negative melody-corruption control.'})
    print('Rechecked existing outputs:',sum(r['technical_pass'] for r in revised['runs']),'/',len(revised['runs']),
          'technical;',sum(r['technical_pass'] for r in audits),'/',len(audits),'raw audit; MIDI hashes unchanged')


if __name__=='__main__':main()
