"""Create tables, per-composition interpretations, and exact-data figures."""
import argparse
import csv
import json
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import mido
import pretty_midi


def encoded_spb(path):
    raw=mido.MidiFile(path)
    return next((m.tempo/1e6 for t in raw.tracks for m in t if m.type=='set_tempo'),0.5)


def piano_roll(root,case_id,rows):
    annotation=json.loads((root/'prepared'/f'{case_id}.json').read_text())
    source=root/'prepared'/f'{case_id}.mid'
    paths=[('Prepared source',source,annotation['melody_track'])]
    for method,label in [('instrument_only','B0: instruments only'),('fixed','B1: fixed patterns'),
                         ('adaptive','M: adaptive, frozen weights'),('no_continuity','Ablation: continuity removed')]:
        row=next(r for r in rows if r['method']==method)
        paths.append((label,root/row['output'],row['trace']['melody_track']))
    figure,axes=plt.subplots(5,1,figsize=(10.6,9),sharex=True,sharey=True)
    for ax,(label,path,melody_index) in zip(axes,paths):
        midi=pretty_midi.PrettyMIDI(str(path));spb=encoded_spb(path)
        for index,track in enumerate(midi.instruments):
            if track.is_drum:continue
            segments=[[(n.start/spb,n.pitch),(n.end/spb,n.pitch)] for n in track.notes]
            ax.add_collection(LineCollection(segments,colors='#125aab' if index==melody_index else '#c17726',
                                            linewidths=1.8 if index==melody_index else 1,alpha=0.9 if index==melody_index else 0.55))
        for bar in [0,4,8,12,16]:ax.axvline(bar*4,color='#888888',lw=0.6,ls='--')
        ax.set_title(label,loc='left',fontsize=10);ax.set_ylabel('MIDI pitch',fontsize=9);ax.set_ylim(23,99)
    axes[-1].set_xlim(0,64);axes[-1].set_xlabel('Beats in prepared excerpt')
    figure.suptitle(case_id.replace('_',' ')+'\nBlue: protected melody; orange: pitched accompaniment. Drums omitted.',fontsize=11)
    figure.tight_layout(rect=(0,0,1,0.94))
    output=root/'figures'/f'{case_id}_comparison.png';output.parent.mkdir(exist_ok=True)
    figure.savefig(output,dpi=160);plt.close(figure)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    root=parser.parse_args().output.resolve()
    report=json.loads((root/'evaluation_rechecked.json').read_text())
    prep=json.loads((root/'preparation.json').read_text())
    selection=json.loads((root/'frozen_selection.json').read_text())
    rows=report['runs'];test=[r for r in rows if r['split']=='test']
    fields=['case_id','split','source_style','target_style','method','technical_pass','transform_seconds',
            'target_reference_distance','accompaniment_events_different_from_fixed',
            'mean_phrase_texture_change_notes_per_bar','mean_boundary_bass_jump_semitones','plans']
    with (root/'per_composition_results.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for row in rows:
            writer.writerow({**{k:row[k] for k in fields if k in row},
                             **{k:row['musical_measurements'][k] for k in fields if k in row['musical_measurements']},
                             'plans':' / '.join(x['plan'] for x in row['trace']['selection'])})
    lines=['# Taimoor: source-derived evaluation checkpoint','',
           'Exploratory progress evidence, not a completed final-project study or a perceptual genre-quality result.','',
           '## What was evaluated','',
           '- 12 distinct compositions from Smit\'s pinned dataset branch: 4 development and 8 held-out for parameter selection, balanced by source folder genre.',
           '- One 16-bar excerpt per composition, approximately 30-60 seconds, with an explicitly selected melody track.',
           '- Four matched conditions: B0 instrument substitution, B1 fixed patterns, adaptive selection, and the continuity ablation.',
           '- Melody/chord/phrase inputs are source-derived with provisional annotations. The four-bar grid is not independently reviewed phrase structure.',
           '- No composition or exact source/prepared/melody-content hash crosses splits. Artist-level independence and alternate-version detection are not established.','',
           '## Development-only parameter selection','',
           'Only the four development compositions informed reference centers/scales and weight selection. Style weight was fixed at 1: globally scaling both weights cannot change the selected path.',
           'The selection proxy combines distance to target-genre development-source descriptors and a separately measured boundary bass-jump penalty. It is not a listener rating or classifier accuracy.','',
           '| Continuity weight | Mean development selection proxy |','| ---: | ---: |']
    for grid in selection['grid']:lines.append(f"| {grid['continuity']:g} | {grid['mean_selection_proxy']:.4f} |")
    lines += ['',f"Selected style/continuity weights: **{selection['selected_weights']['style']:g} / {selection['selected_weights']['continuity']:g}**. Frozen selection and all original MIDI hashes are retained.",
              'The selected continuity weight is at the upper grid boundary; it is a choice within this grid, not a demonstrated global optimum.','',
              '## Technical verification','',
              f"All **{sum(r['technical_pass'] for r in rows)}/{len(rows)}** conditions pass the corrected generator checks; all **{sum(r['technical_pass'] for r in report['raw_midi_audit'])}/{len(report['raw_midi_audit'])}** pass the independent raw-event audit.",
              'The audit finds zero melody pitch/onset/offset/velocity event differences. Tempo, metre, endpoints and supplied grid markers are retained. Generated B1/M/ablation accompaniment has no annotated chord-membership, register, or event-bound violations.',
              'B0 retains original accompaniment. Original non-chord tones and source registers are measured, but they are not violations of the generator-only constraints.','',
              '### Diagnostic correction retained in the record','',
              'The first pass recorded 36/48 generator-check passes and 32/48 raw-audit passes. A BPM-float versus integer-MIDI-tempo discrepancy caused false bar-boundary harmony flags and false duration failures.',
              'The corrected measurement reads encoded MIDI timing. Rechecking the identical saved files gives 48/48 passes in both checks; no arrangement or parameter was changed. Decimal-tempo regression cases were added. Future exports also round constant MIDI tempo rather than truncating it.',
              'Because the measurement correction followed inspection of test diagnostics, these are diagnostic pilot results, not a pristine confirmatory hold-out experiment. The original evaluation, frozen selection, first-run code and repair record are preserved.','',
              '## Held-out comparisons','',
              'Each row below is averaged over eight test compositions. Lower descriptor distance indicates greater similarity to the small development reference profile, not proven genre quality. Lower texture change is not necessarily musically preferable.','',
              '| Method | Target-reference distance | Texture change (notes/bar) | Boundary bass jump (semitones) | Transform time (ms) |',
              '| --- | ---: | ---: | ---: | ---: |']
    for method in ['instrument_only','fixed','adaptive','no_continuity']:
        group=[r for r in test if r['method']==method]
        lines.append(f"| {method} | {mean(r['target_reference_distance'] for r in group):.3f} | {mean(r['musical_measurements']['mean_phrase_texture_change_notes_per_bar'] for r in group):.2f} | {mean(r['musical_measurements']['mean_boundary_bass_jump_semitones'] for r in group):.2f} | {1000*mean(r['transform_seconds'] for r in group):.2f} |")
    changed=sum(r['accompaniment_events_different_from_fixed']>0 for r in test if r['method']=='adaptive')
    lines += ['',f'Adaptive selection differs from the fixed arrangement in **{changed}/8** held-out compositions. Matching B1 on the others is a valid result: context-aware selection does not guarantee a different plan.',
              'Descriptor evidence does not justify claiming superiority to instrument substitution. No statistical significance, genre-recognition accuracy, or listener preference is claimed.','',
              '## Per-composition ablation interpretation','',
              '| Composition | Adaptive phrase plans | Events different from fixed | Texture: full / no-continuity | Bass jumps: full / no-continuity |',
              '| --- | --- | ---: | ---: | ---: |']
    for case in sorted({r['case_id'] for r in test}):
        group={r['method']:r for r in test if r['case_id']==case};a=group['adaptive'];n=group['no_continuity']
        am=a['musical_measurements'];nm=n['musical_measurements']
        lines.append(f"| {a['composition_id']} | {' / '.join(x['plan'] for x in a['trace']['selection'])} | {a['accompaniment_events_different_from_fixed']} | {am['mean_phrase_texture_change_notes_per_bar']:.2f} / {nm['mean_phrase_texture_change_notes_per_bar']:.2f} | {am['mean_boundary_bass_jump_semitones']:.2f} / {nm['mean_boundary_bass_jump_semitones']:.2f} |")
    lines += ['']
    for case in sorted({r['case_id'] for r in test}):
        group={r['method']:r for r in test if r['case_id']==case};a=group['adaptive'];n=group['no_continuity'];f=group['fixed']
        am=a['musical_measurements'];nm=n['musical_measurements'];delta=am['mean_phrase_texture_change_notes_per_bar']-nm['mean_phrase_texture_change_notes_per_bar']
        comparison='reduces' if delta < -1e-6 else 'increases' if delta > 1e-6 else 'does not change'
        lines.append(f"- **{a['composition_id']}:** continuity {comparison} the measured phrase-to-phrase texture change ({am['mean_phrase_texture_change_notes_per_bar']:.2f} versus {nm['mean_phrase_texture_change_notes_per_bar']:.2f} notes/bar). The target-reference distance is {a['target_reference_distance']:.3f}, compared with {f['target_reference_distance']:.3f} for fixed patterns and {n['target_reference_distance']:.3f} without continuity. These numbers describe an arrangement trade-off; auditory coherence has not been rated.")
    flagged=sum(r['flagged_bars'] for r in prep['prepared'])
    lines += ['', '## Annotation and interpretation limits','',
              f"The conservative chord estimator flags **{flagged}/192 bars** for review because of low candidate separation, low coverage or disagreement between half bars. A flag is uncertainty, not proof of a wrong chord.",
              'Per-bar chords approximate some within-bar changes. Annotated-harmony compliance establishes consistency with those supplied estimates; it does not prove that the original source harmony is fully preserved.',
              'Source genre folders are Smit\'s labels, not newly validated genre ground truth. MIDI acquisition/provenance beyond the pinned team commit still requires Smit\'s documentation.',
              'The original 60-composition dataset, independently reviewed musical annotations, and structured external listening remain outstanding. The four synthetic cases remain useful unit-test demonstrations and are not counted among these 12 source-derived compositions.','',
              '## Updated indicator assessment','',
              '| Indicator | Evidence now available | Scope / remaining limitation |','| --- | --- | --- |',
              '| O1 PI1 basic | Representation, interfaces, source-derived annotation examples | Shared annotation review remains pending |',
              '| O1 PI2 basic | Adaptation, preservation, independent checks, decimal-tempo correction | Preservation of supplied annotations rather than verified original harmony |',
              '| O1 PI3 expected | Descriptor-distance selection, 8 development-only weight settings, frozen configuration | Small proxy-based selection; hand-authored pattern library |',
              '| O1 PI4 expected | DP, transitions, exact repeated-pattern constraint, both target styles | Synthetic repeat tests; provisional real-source grid boundaries |',
              '| O2 PI1 basic | Matched B0/B1/M conditions, controlled input/library/palette | Pilot protocol explicitly smaller than final study |',
              '| O2 PI2 basic | IDs, settings, hashes, traces, times, retained failures and corrections | All evidence is reproducible from pinned sources |',
              '| O2 PI3 expected | 8 composition-separated test cases in both directions; failures, invariants, changes, runtime | Exploratory diagnostic checkpoint; annotation and perceptual caveats |',
              '| O2 PI4 expected | Fixed-selection and continuity ablations; per-composition symbolic interpretation | Specific listener observations remain to be recorded |',
              '| Advanced | No learned reranker/pretrained comparison is claimed | Weight grid is a pilot, not a completed robust final sensitivity study |','',
              '## Attribution','',
              '- Smit: source MIDI collection and initial inspection, revision 3316077bdd47621f2eb9a506ee2900c0bb94dfe4.',
              '- Vinay: unchanged accompaniment feature extractor, revision dcf7a4218243606e79055212830e08f4bfd9ff55; used here for a transparent descriptor proxy, not a trained classifier result.',
              '- Taimoor workstream: input adapter/cropping, provisional annotations, constrained arrangement, development selection, controlled comparisons, audits, diagnostic fixes and interpretation.',
              '- Abdullah: pinned rendering implementation used for the listening materials; no new audio or UI implementation is attributed to Taimoor.','']
    (root/'EVALUATION_SUMMARY.md').write_text('\n'.join(lines),encoding='utf-8')
    for case in ['jazz_Let_There_Be_Love','rock_Brain_Stew']:
        piano_roll(root,case,[r for r in rows if r['case_id']==case])
    plt.rcParams.update({'font.size':10})
    figure,axes=plt.subplots(1,2,figsize=(10,3.8))
    grid=selection['grid'];axes[0].plot([g['continuity'] for g in grid],[g['mean_selection_proxy'] for g in grid],'o-',color='#125aab')
    axes[0].set(xlabel='Continuity weight (style weight = 1)',ylabel='Development selection proxy',title='Four development compositions only')
    labels=[r['composition_id'] for r in test if r['method']=='adaptive']
    x=list(range(len(labels)))
    for offset,(method,label) in zip([-0.18,0.18],[('adaptive','Full'),('no_continuity','No continuity')]):
        values=[next(r for r in test if r['composition_id']==c and r['method']==method)['musical_measurements']['mean_phrase_texture_change_notes_per_bar'] for c in labels]
        axes[1].bar([i+offset for i in x],values,width=0.36,label=label)
    axes[1].set_xticks(x,[str(i+1) for i in x]);axes[1].set(xlabel='Held-out composition (CSV order)',ylabel='Texture change (notes/bar)',title='Ablation: descriptive, not preference');axes[1].legend()
    figure.tight_layout();figure.savefig(root/'figures'/'selection_and_ablation.png',dpi=180);plt.close(figure)
    print('Wrote summary, per-composition CSV and three figures')


if __name__=='__main__':main()
