"""Export compact development evidence and a renderer handoff, without fitting.

Paired bootstrap intervals resample compositions and are descriptive development
diagnostics. They are not a final significance test or human-quality evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import shutil

import numpy as np

from workstreams.taimoor.advanced_study import COMPARISON_METHODS
from workstreams.taimoor.team_handoff import dump, sha


def paired_differences(runs, baseline, condition, field, expected):
    left = {r['case_id']: r for r in runs if r['condition']==baseline}
    right = {r['case_id']: r for r in runs if r['condition']==condition}
    if set(left) != set(right) or len(left) != expected:
        raise ValueError('Paired summary requires every planned composition in both conditions')
    def get(row):
        for name in field.split('.'):
            row = row[name]
        return float(row)
    values = np.array([get(right[k])-get(left[k]) for k in sorted(left)])
    if not np.isfinite(values).all():
        raise ValueError('Nonfinite paired metric')
    return values


def interval(values, seed=42, replicates=2000):
    if len(values) < 2:
        raise ValueError('A composition interval needs at least two paired observations')
    values = np.asarray(values, dtype=float)
    indices = np.random.default_rng(seed).integers(0,len(values),size=(replicates,len(values)))
    means = values[indices].mean(axis=1)
    low, high = np.quantile(means,[.025,.975])
    return {'paired_compositions':len(values),'mean_difference':float(values.mean()),
            'bootstrap_95_percent_interval':[float(low),float(high)],
            'bootstrap_replicates':replicates,'seed':seed}


def export(advanced, handoff, proposal, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Export to a new empty evidence directory')
    comparison_path=advanced/'comparison/comparison_results.json'
    comparison=json.loads(comparison_path.read_text())
    roles=json.loads((advanced/'development_roles.json').read_text())
    grid=json.loads((advanced/'sensitivity/grid_results.json').read_text())
    selection=json.loads((advanced/'development_selection.json').read_text())
    if (sha(advanced/'sensitivity/grid_results.json') != selection['grid_results_sha256'] or
            sha(advanced/'model_manifest.json') != selection['model_manifest_sha256'] or
            comparison['selection_sha256'] != sha(advanced/'development_selection.json')):
        raise ValueError('Development evidence no longer matches its frozen artifact hashes')
    if comparison['failures'] or grid['failures'] or not all(c['eligible'] for c in grid['configurations']):
        raise ValueError('Do not export an incomplete or technically failing development study')
    n=len(roles['checks'])
    if len(comparison['runs']) != n*len(COMPARISON_METHODS) or len(comparison['raw_midi_audit']) != n*len(COMPARISON_METHODS):
        raise ValueError('Matched comparison denominator is incomplete')
    if not all(r['technical_pass'] for r in comparison['runs']+comparison['raw_midi_audit']):
        raise ValueError('Matched comparison contains a technical failure')
    metrics=('target_reference_distance','selection_proxy',
             'boundary.mean_phrase_texture_change_notes_per_bar','boundary.mean_boundary_bass_jump_semitones')
    uncertainty=[]
    for condition in ('learned','development_selected'):
        for field in metrics:
            differences=paired_differences(comparison['runs'],'adaptive',condition,field,n)
            uncertainty.append({'condition':condition,'baseline':'adaptive','metric':field,
                                **interval(differences)})
    output.mkdir(parents=True)
    for name in ['protocol.json','model_manifest.json','classifier_cv.json',
                 'development_classifier_check.json','development_selection.json']:
        shutil.copyfile(advanced/name,output/name)
    shutil.copyfile(advanced/'sensitivity/grid_summary.csv',output/'grid_summary.csv')
    shutil.copyfile(advanced/'sensitivity/strata_summary.csv',output/'strata_summary.csv')
    shutil.copyfile(advanced/'comparison/summary.csv',output/'comparison_summary.csv')
    shutil.copyfile(comparison_path,output/'comparison_results.json')
    dump(output/'paired_development_intervals.json',{
        'scope':'Exploratory paired composition bootstrap on internal development examples',
        'difference':'condition minus heuristic adaptive; smaller structural metrics are not necessarily better music',
        'limitation':'Small development sample; selected-condition intervals do not correct for configuration selection',
        'results':uncertainty})
    dump(output/'development_roles.json',{
        'fitting_cases':[r['case_id'] for r in roles['fitting']],
        'development_check_cases':[r['case_id'] for r in roles['checks']],
        'original_split_for_all_cases':'train',
        'inputs':[{'case_id':r['case_id'],'midi_sha256':r['prepared_sha256'],
                   'annotation_sha256':r['annotation_sha256']} for r in roles['fitting']+roles['checks']]})
    for name in ['split_proposal.json','annotation_review.csv','readiness.json']:
        shutil.copyfile(proposal/name,output/name)
    with (proposal/'proposed_manifest.csv').open(newline='',encoding='utf-8') as handle:
        reader=csv.DictReader(handle);fields=reader.fieldnames;proposed_rows=list(reader)
    with (output/'proposed_manifest.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for row in proposed_rows:
            row['midi_path']=os.path.relpath((proposal/row['midi_path']).resolve(),output.resolve())
            writer.writerow(row)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    configurations=grid['configurations']
    continuities=sorted({r['continuity'] for r in configurations})
    betas=sorted({r['reranker_weight'] for r in configurations})
    matrix=np.array([[next(r['mean_selection_proxy'] for r in configurations
                           if r['continuity']==c and r['reranker_weight']==b) for b in betas] for c in continuities])
    fig,ax=plt.subplots(figsize=(4.8,5.2))
    heat=ax.imshow(matrix,cmap='viridis_r',aspect='auto')
    for i in range(len(continuities)):
        for j in range(len(betas)):
            ax.text(j,i,f'{matrix[i,j]:.3f}',ha='center',va='center',fontsize=8,
                    color='white' if matrix[i,j] > np.median(matrix) else 'black')
    chosen=selection['selected_configuration']
    i,j=continuities.index(chosen['continuity']),betas.index(chosen['reranker_weight'])
    ax.add_patch(Rectangle((j-.48,i-.48),.96,.96,fill=False,edgecolor='#ff5b35',linewidth=2))
    ax.set_xticks(range(len(betas)),[f'{x:g}' for x in betas])
    ax.set_yticks(range(len(continuities)),[f'{x:g}' for x in continuities])
    ax.set_xlabel('Learned penalty weight (beta)');ax.set_ylabel('Continuity weight (lambda)')
    ax.set_title(f'Internal development sensitivity (n={n})\nStyle weight = 1; not a listening-quality score',fontsize=10)
    fig.colorbar(heat,ax=ax,label='Mean structural selection proxy')
    fig.tight_layout();fig.savefig(output/'sensitivity_grid.png',dpi=180);plt.close(fig)
    with (output/'render_handoff.csv').open('w',newline='',encoding='utf-8') as handle:
        fields=['case_id','condition','midi_path','midi_sha256','melody_track_index','source_midi_path',
                'sample_rate','target_lufs','tail_seconds','audio_status']
        writer=csv.DictWriter(handle,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for record in roles['checks']:
            source=(handoff/record['midi']).resolve()
            relative_source=os.path.relpath(source,output.resolve())
            writer.writerow({'case_id':record['case_id'],'condition':'source','midi_path':relative_source,
                             'midi_sha256':sha(source),'melody_track_index':record['melody_track'],
                             'source_midi_path':relative_source,'sample_rate':44100,'target_lufs':-23,
                             'tail_seconds':.5,'audio_status':'not_rendered'})
            for row in [r for r in comparison['runs'] if r['case_id']==record['case_id']]:
                path=(advanced/'comparison/outputs'/record['case_id']/(row['condition']+'.mid')).resolve()
                if sha(path)!=row['output_sha256']:
                    raise ValueError('Comparison output changed before renderer handoff')
                writer.writerow({'case_id':record['case_id'],'condition':row['condition'],
                                 'midi_path':os.path.relpath(path,output.resolve()),'midi_sha256':sha(path),
                                 'melody_track_index':row['trace']['melody_track'],'source_midi_path':relative_source,
                                 'sample_rate':44100,'target_lufs':-23,'tail_seconds':.5,'audio_status':'not_rendered'})
    manifest={'scope':'Development prototype evidence; final data and listening reviews pending',
              'grid_conditions':len(grid['rows']),'matched_conditions':len(comparison['runs']),
              'model_binary_committed':False,'generated_midi_committed':False,
              'source_records_sha256':{'grid_results.json':sha(advanced/'sensitivity/grid_results.json'),
                                       'comparison_results.json':sha(comparison_path),
                                       'proposed_manifest.csv':sha(proposal/'proposed_manifest.csv')},
              'path_policy':'Renderer and proposed MIDI paths are rebased relative to their exported CSV files',
              'export_script_sha256':sha(Path(__file__)),
              'selected_configuration':selection['selected_configuration'],
              'exported_file_sha256':{p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()}}
    dump(output/'evidence_manifest.json',manifest)
    print('Exported',len(manifest['exported_file_sha256']),'evidence files;',n*(len(COMPARISON_METHODS)+1),'pending renderer rows')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--advanced',type=Path,required=True)
    parser.add_argument('--handoff',type=Path,required=True)
    parser.add_argument('--proposal',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    export(args.advanced.resolve(),args.handoff.resolve(),args.proposal.resolve(),args.output.resolve())


if __name__=='__main__':
    main()
