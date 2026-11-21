"""Training-pool development model, sensitivity grid and matched comparisons.

No command in this module generates final validation/test outputs. The model,
internal development split and chosen settings are provisional until the team
agrees reviewed inputs and a final evaluation protocol.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import time

import joblib
import numpy as np
import pandas as pd
import pretty_midi
import sklearn
from sklearn.base import clone
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold

from .arranger import Weights, arrange
from .checkpoint import boundary_metrics, valid
from .evaluate import measure
from .independent_audit import audit_case
from .learned_ranking import LearnedPenalty, anchored_features, load_vinay
from .model import load_song, write_midi
from .team_handoff import SMIT_REVISION, dump, inside, sha


HERE = Path(__file__).parent
PROTOCOL = HERE / 'advanced_protocol.json'
COMPARISON_METHODS = ('instrument_only', 'fixed', 'adaptive', 'no_continuity',
                      'learned', 'development_selected')


def code_hashes():
    return {p.name: sha(p) for p in sorted(HERE.glob('*.py'))} | {PROTOCOL.name: sha(PROTOCOL)}


def development_roles(records, checks_per_genre=5, seed=42):
    """Choose roles from original training records before opening any input."""
    training = [r for r in records if r['split'] == 'train']
    grouped = defaultdict(list)
    for row in training:
        grouped[row['composition_key']].append(row)
    if any(len({r['source_style'] for r in group}) != 1 for group in grouped.values()):
        raise ValueError('A training composition group has conflicting genre labels')
    checks = set()
    for genre in ('jazz', 'rock'):
        names = [k for k, group in grouped.items() if group[0]['source_style'] == genre]
        names.sort(key=lambda key: hashlib.sha256(f'{seed}:{key}'.encode()).hexdigest())
        if len(names) <= checks_per_genre + 2:
            raise ValueError('Insufficient independent training groups for fitting and development checks')
        checks.update(names[:checks_per_genre])
    fit = [r for r in training if r['composition_key'] not in checks]
    check = [r for r in training if r['composition_key'] in checks]
    assert not {r['composition_key'] for r in fit} & {r['composition_key'] for r in check}
    return fit, check


def verify_training_inputs(handoff, records):
    for row in records:
        if row['split'] != 'train':
            raise ValueError('Development runner refuses original validation/test records')
        if sha(inside(handoff, row['annotation'])) != row['annotation_sha256'] or sha(
                inside(handoff, row['midi'])) != row['prepared_sha256']:
            raise ValueError('Training input changed after its handoff audit')


def feature_frame(handoff, records, team):
    verify_training_inputs(handoff, records)
    rows = []
    for record in records:
        song = load_song(handoff / record['annotation'])
        features = anchored_features(team, song.midi, song.melody_track,
                                     song.duration_beats*song.seconds_per_beat)
        rows.append({'case_id': song.case_id, 'composition_id': record['composition_key'],
                     'genre': song.source_style, **features})
    return pd.DataFrame(rows)


def vector(features, tempo):
    return np.array([features['note_density'], features['average_polyphony'],
                     features['offbeat_activity'], features['average_note_duration']*tempo/60], dtype=float)


def input_properties(song):
    changes = sum(a != b for a, b in zip(song.chords, song.chords[1:])) / max(1, song.bars-1)
    extended = sum(len(c.intervals) > 3 for c in song.chords) / song.bars
    return {'melody_density': len(song.melody.notes)/song.duration_beats,
            'harmony_complexity': changes+extended}


def make_references(handoff, records, team, protocol):
    values = {'jazz': [], 'rock': []}
    properties = []
    for record in records:
        song = load_song(handoff / record['annotation'])
        features = anchored_features(team, song.midi, song.melody_track,
                                     song.duration_beats*song.seconds_per_beat)
        values[song.source_style].append(vector(features, song.tempo))
        properties.append(input_properties(song))
    all_values = np.vstack([v for group in values.values() for v in group])
    return {'fitting_cases': [r['case_id'] for r in records],
            'centers': {style: np.mean(v, axis=0).tolist() for style, v in values.items()},
            'scale': np.maximum(np.std(all_values, axis=0), protocol['descriptor_scale_floor']).tolist(),
            'strata_thresholds': {k: float(np.median([p[k] for p in properties])) for k in properties[0]}}


def strata(song, references):
    p = input_properties(song)
    return {'direction': song.source_style + '_to_' + ('rock' if song.source_style == 'jazz' else 'jazz'),
            **{k: 'low' if value <= references['strata_thresholds'][k] else 'high' for k, value in p.items()}}


def model_selection(frame, team, protocol):
    names = team.classifier.FEATURE_NAMES
    folds = list(StratifiedGroupKFold(n_splits=protocol['cross_validation_folds'], shuffle=True,
                                    random_state=protocol['seed']).split(
                                        frame[names], frame['genre'], frame['composition_id']))
    scores, records = {}, []
    models = team.classifier.create_models()
    for name, model in models.items():
        scores[name] = []
        for index, (fit, held) in enumerate(folds):
            if set(frame.iloc[fit]['composition_id']) & set(frame.iloc[held]['composition_id']):
                raise ValueError('Composition leakage in classifier cross-validation')
            fitted = clone(model).fit(frame.iloc[fit][names], frame.iloc[fit]['genre'])
            predictions = fitted.predict(frame.iloc[held][names])
            score = float(f1_score(frame.iloc[held]['genre'], predictions, labels=['jazz', 'rock'],
                                   average='macro', zero_division=0))
            scores[name].append(score)
            records.append({'model': name, 'fold': index, 'macro_f1': score,
                            'fitting_cases': frame.iloc[fit]['case_id'].tolist(),
                            'held_out_cases': frame.iloc[held]['case_id'].tolist()})
    means = {name: float(np.mean(v)) for name, v in scores.items()}
    best = min(means, key=lambda name: (-means[name], name != 'logistic_regression', name))
    model = clone(models[best]).fit(frame[names], frame['genre'])
    return model, {'selected_model': best, 'mean_cv_macro_f1': means, 'folds': records,
                   'scope': 'Grouped cross-validation inside the original training pool; not final test results'}


def fit_development(handoff, root, vinay_root):
    if root.exists() and any(root.iterdir()):
        raise ValueError('Use a new empty advanced-study directory')
    protocol = json.loads(PROTOCOL.read_text())
    audit = json.loads((handoff/'handoff_audit.json').read_text())
    if audit['source_revision'] != SMIT_REVISION or audit['failures']:
        raise ValueError('Invalid source handoff revision or unresolved input failures')
    fitting, checks = development_roles(audit['records'], protocol['development_checks_per_genre'], protocol['seed'])
    # No feature or model function is passed the original validation/test rows.
    verify_training_inputs(handoff, fitting+checks)
    team = load_vinay(vinay_root)
    root.mkdir(parents=True, exist_ok=True)
    dump(root/'protocol.json', protocol)
    dump(root/'development_roles.json', {'fitting': fitting, 'checks': checks,
                                        'original_split_required': 'train'})
    frame = feature_frame(handoff, fitting, team)
    frame.to_csv(root/'training_features.csv', index=False, lineterminator='\n')
    model, cv = model_selection(frame, team, protocol)
    dump(root/'classifier_cv.json', cv)
    check_frame = feature_frame(handoff, checks, team)
    predictions = model.predict(check_frame[team.classifier.FEATURE_NAMES])
    check_report = {'scope': 'Internal development diagnostics; not the project held-out test set',
                    'macro_f1': float(f1_score(check_frame['genre'], predictions, labels=['jazz','rock'],
                                               average='macro', zero_division=0)),
                    'confusion_matrix_labels': ['jazz','rock'],
                    'confusion_matrix': confusion_matrix(check_frame['genre'], predictions,
                                                        labels=['jazz','rock']).tolist(),
                    'predictions': [{'case_id': r['case_id'], 'source_label': r['genre'], 'prediction': str(p)}
                                    for r, p in zip(check_frame.to_dict('records'), predictions)]}
    dump(root/'development_classifier_check.json', check_report)
    dump(root/'references.json', make_references(handoff, fitting, team, protocol))
    joblib.dump(model, root/'development_model.joblib')
    manifest = {'scope': protocol['scope'], 'provisional_model': True,
                'selected_model': cv['selected_model'], 'vinay_revision': team.revision,
                'teammate_code_sha256': team.hashes, 'feature_names': team.classifier.FEATURE_NAMES,
                'handoff_audit_sha256': sha(handoff/'handoff_audit.json'),
                'model_sha256': sha(root/'development_model.joblib'),
                'protocol_sha256': sha(root/'protocol.json'), 'code_sha256': code_hashes(),
                'roles_sha256': sha(root/'development_roles.json'),
                'references_sha256': sha(root/'references.json'),
                'training_features_sha256': sha(root/'training_features.csv'),
                'fitting_cases': [r['case_id'] for r in fitting],
                'development_check_cases': [r['case_id'] for r in checks],
                'original_validation_test_inputs_used': False,
                'runtime': {'python': platform.python_version(), 'numpy': np.__version__,
                            'pandas': pd.__version__, 'scikit_learn': sklearn.__version__,
                            'pretty_midi': pretty_midi.__version__}}
    dump(root/'model_manifest.json', manifest)
    print(f"Fitted {cv['selected_model']} on {len(fitting)} training compositions; "
          f"internal development checks: {len(checks)}; source-label macro-F1 {check_report['macro_f1']:.3f}")
    return manifest


def validated_run(handoff, root, vinay_root):
    manifest = json.loads((root/'model_manifest.json').read_text())
    expected = {'development_model.joblib': 'model_sha256', 'protocol.json': 'protocol_sha256',
                'development_roles.json': 'roles_sha256', 'references.json': 'references_sha256',
                'training_features.csv': 'training_features_sha256'}
    if manifest['code_sha256'] != code_hashes() or sha(handoff/'handoff_audit.json') != manifest['handoff_audit_sha256']:
        raise ValueError('Code or handoff changed after model fitting; create a fresh development run')
    for file, key in expected.items():
        if sha(root/file) != manifest[key]:
            raise ValueError('Frozen development artifact changed: ' + file)
    roles = json.loads((root/'development_roles.json').read_text())
    verify_training_inputs(handoff, roles['fitting']+roles['checks'])
    team = load_vinay(vinay_root)
    if team.hashes != manifest['teammate_code_sha256'] or team.classifier.FEATURE_NAMES != manifest['feature_names']:
        raise ValueError('Teammate feature/model contract changed')
    # This is our own fitted, hash-verified local artifact, not an external model.
    model = joblib.load(root/'development_model.joblib')
    return (team, model, roles, json.loads((root/'protocol.json').read_text()),
            json.loads((root/'references.json').read_text()))


def output_metrics(song, path, melody_index, team, references):
    metrics, signature = measure(song, path, melody_index)
    output = pretty_midi.PrettyMIDI(str(path))
    features = anchored_features(team, output, melody_index, song.duration_beats*song.seconds_per_beat)
    target = 'jazz' if song.source_style == 'rock' else 'rock'
    d = float(np.sqrt(np.mean(((vector(features, song.tempo)-references['centers'][target]) /
                               np.asarray(references['scale']))**2)))
    boundary = boundary_metrics(output, melody_index, song)
    return {'metrics': metrics, 'target_reference_distance': d, 'boundary': boundary,
            'selection_proxy': d+0.25*boundary['mean_boundary_bass_jump_semitones']/12}, signature


def summarize_grid(rows, expected):
    complete = len(rows) == expected and all(r['technical_pass'] and r['raw_audit']['technical_pass'] for r in rows)
    return {'eligible': complete, 'completed_conditions': len(rows), 'planned_conditions': expected,
            'mean_selection_proxy': float(np.mean([r['selection_proxy'] for r in rows])) if complete else None}


def sensitivity(handoff, root, vinay_root):
    team, model, roles, protocol, references = validated_run(handoff, root, vinay_root)
    directory = root/'sensitivity'
    if directory.exists():
        raise ValueError('Existing sensitivity evidence is immutable')
    directory.mkdir()
    all_rows, grid, failures, cache = [], [], [], {}
    for continuity in protocol['continuity_grid']:
        for beta in protocol['reranker_weight_grid']:
            key = f'c{continuity:g}_b{beta:g}'
            scorer = LearnedPenalty(team, model, beta, cache) if beta else None
            rows = []
            for record in roles['checks']:
                try:
                    song = load_song(handoff/record['annotation'])
                    target = 'jazz' if song.source_style == 'rock' else 'rock'
                    weights = Weights(protocol['style_weight'], continuity)
                    started = time.perf_counter()
                    midi, trace = arrange(song, target, weights=weights, candidate_scorer=scorer)
                    elapsed = time.perf_counter()-started
                    path = directory/key/'outputs'/song.case_id/'adaptive.mid'
                    write_midi(midi, path, song.duration_beats, song.phrases)
                    values, _ = output_metrics(song, path, trace['melody_track'], team, references)
                    audit = audit_case(handoff/record['annotation'], directory/key/'outputs', methods=('adaptive',))[0]
                    row = {'case_id': song.case_id, 'original_split': song.split,
                           'continuity': continuity, 'reranker_weight': beta, 'strata': strata(song, references),
                           'technical_pass': valid(values['metrics'], 'adaptive'), 'raw_audit': audit,
                           'output_sha256': sha(path), 'transform_seconds': elapsed,
                           'plans': [c['plan'] for c in trace['selection']], **values}
                    rows.append(row)
                except Exception as exc:
                    failures.append({'case_id': record['case_id'], 'configuration': key,
                                     'error': f'{type(exc).__name__}: {exc}'})
            grid.append({'continuity': continuity, 'reranker_weight': beta, **summarize_grid(rows, len(roles['checks']))})
            all_rows.extend(rows)
    dump(directory/'grid_results.json', {'scope': protocol['scope'], 'rows': all_rows,
                                          'configurations': grid, 'failures': failures})
    pd.DataFrame(grid).to_csv(directory/'grid_summary.csv', index=False, lineterminator='\n')
    strata_rows = []
    for axis in ('direction', 'melody_density', 'harmony_complexity'):
        groups = defaultdict(list)
        for row in all_rows:
            groups[(row['continuity'], row['reranker_weight'], row['strata'][axis])].append(row)
        for (continuity, beta, value), rows in sorted(groups.items()):
            strata_rows.append({'axis': axis, 'stratum': value, 'continuity': continuity,
                                'reranker_weight': beta, 'cases': len(rows),
                                'mean_selection_proxy': float(np.mean([r['selection_proxy'] for r in rows])),
                                'technical_passes': sum(r['technical_pass'] for r in rows),
                                'raw_audit_passes': sum(r['raw_audit']['technical_pass'] for r in rows)})
    pd.DataFrame(strata_rows).to_csv(directory/'strata_summary.csv', index=False, lineterminator='\n')
    eligible = [r for r in grid if r['eligible']]
    if failures or len(eligible) != len(grid):
        raise SystemExit('Sensitivity failures recorded; resolve them before freezing any development selection')
    best = min(eligible, key=lambda r: (r['mean_selection_proxy'], r['reranker_weight'], r['continuity']))
    frozen = {'scope': 'Internal development selection only; not an approved final configuration',
              'selected_configuration': best, 'model_manifest_sha256': sha(root/'model_manifest.json'),
              'grid_results_sha256': sha(directory/'grid_results.json'),
              'protocol_sha256': sha(root/'protocol.json'), 'code_sha256': code_hashes(),
              'fitting_cases': [r['case_id'] for r in roles['fitting']],
              'selection_cases': [r['case_id'] for r in roles['checks']],
              'original_validation_test_cases_used': False, 'strata_thresholds': references['strata_thresholds'],
              'final_evaluation_ready': False, 'quality_claim': protocol['quality_claim']}
    dump(root/'development_selection.json', frozen)
    print(f"Development grid: {len(all_rows)}/{len(grid)*len(roles['checks'])}; "
          f"selected continuity={best['continuity']}, beta={best['reranker_weight']}; failures={len(failures)}")
    return frozen


def compare(handoff, root, vinay_root):
    team, model, roles, protocol, references = validated_run(handoff, root, vinay_root)
    frozen = json.loads((root/'development_selection.json').read_text())
    if frozen['code_sha256'] != code_hashes() or frozen['model_manifest_sha256'] != sha(root/'model_manifest.json') or (
            frozen['grid_results_sha256'] != sha(root/'sensitivity/grid_results.json')):
        raise ValueError('Selection or sensitivity inputs changed before matched comparison')
    directory = root/'comparison'
    if directory.exists():
        raise ValueError('Existing matched comparison evidence is immutable')
    directory.mkdir()
    runs, audits, failures, cache = [], [], [], {}
    for record in roles['checks']:
        song = load_song(handoff/record['annotation'])
        target = 'jazz' if song.source_style == 'rock' else 'rock'
        signatures = {}
        for condition in COMPARISON_METHODS:
            try:
                beta, continuity = 0, protocol['matched_comparison_continuity']
                if condition == 'learned':
                    beta = protocol['matched_comparison_reranker_weight']
                elif condition == 'development_selected':
                    beta = frozen['selected_configuration']['reranker_weight']
                    continuity = frozen['selected_configuration']['continuity']
                method = condition if condition in ('instrument_only','fixed','no_continuity') else 'adaptive'
                scorer = LearnedPenalty(team, model, beta, cache) if beta else None
                started = time.perf_counter()
                midi, trace = arrange(song, target, method, Weights(protocol['style_weight'], continuity),
                                      candidate_scorer=scorer)
                elapsed = time.perf_counter()-started
                path = directory/'outputs'/song.case_id/(condition+'.mid')
                write_midi(midi, path, song.duration_beats, song.phrases)
                values, signature = output_metrics(song, path, trace['melody_track'], team, references)
                signatures[condition] = signature
                runs.append({'case_id': song.case_id, 'condition': condition, 'source_style': song.source_style,
                             'original_split': song.split, 'target_style': target, 'reranker_weight': beta,
                             'continuity': 0 if method == 'no_continuity' else continuity,
                             'technical_pass': valid(values['metrics'], method), 'trace': trace,
                             'output_sha256': sha(path), 'transform_seconds': elapsed, **values})
            except Exception as exc:
                failures.append({'case_id': song.case_id, 'condition': condition,
                                 'error': f'{type(exc).__name__}: {exc}'})
        for row in [r for r in runs if r['case_id'] == song.case_id]:
            if 'adaptive' in signatures:
                signature = signatures[row['condition']]
                row['accompaniment_events_different_from_adaptive'] = (
                    sum((signature-signatures['adaptive']).values())+sum((signatures['adaptive']-signature).values()))
        try:
            audits.extend(audit_case(handoff/record['annotation'], directory/'outputs', methods=COMPARISON_METHODS))
        except Exception as exc:
            failures.append({'case_id': song.case_id, 'stage': 'raw_audit', 'error': f'{type(exc).__name__}: {exc}'})
    summary = []
    for condition in COMPARISON_METHODS:
        rows = [r for r in runs if r['condition'] == condition]
        summary.append({'condition': condition, 'planned_cases': len(roles['checks']), 'completed_cases': len(rows),
                        'technical_passes': sum(r['technical_pass'] for r in rows),
                        'raw_audit_passes': sum(r['technical_pass'] for r in audits if r['method'] == condition),
                        'mean_target_reference_distance': float(np.mean([r['target_reference_distance'] for r in rows])) if rows else None,
                        'mean_texture_change': float(np.mean([r['boundary']['mean_phrase_texture_change_notes_per_bar'] for r in rows])) if rows else None,
                        'mean_bass_jump': float(np.mean([r['boundary']['mean_boundary_bass_jump_semitones'] for r in rows])) if rows else None,
                        'changed_cases_from_adaptive': sum(r.get('accompaniment_events_different_from_adaptive',0)>0 for r in rows)})
    report = {'scope': protocol['scope'], 'planned_conditions': len(roles['checks'])*len(COMPARISON_METHODS),
              'runs': runs, 'raw_midi_audit': audits, 'summary': summary, 'failures': failures,
              'selection_sha256': sha(root/'development_selection.json'),
              'independent_quality_evaluation_completed': False,
              'interpretation': 'Learned scores guide generation. Structural proxies and these development comparisons do not establish perceptual superiority.'}
    dump(directory/'comparison_results.json', report)
    pd.DataFrame(summary).to_csv(directory/'summary.csv', index=False, lineterminator='\n')
    print(f"Matched development conditions: {len(runs)}/{report['planned_conditions']}; "
          f"technical {sum(r['technical_pass'] for r in runs)}; raw audit {sum(r['technical_pass'] for r in audits)}/{len(audits)}")
    if failures or not all(r['technical_pass'] for r in runs+audits):
        raise SystemExit('Matched comparison has recorded technical failures')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('fit-development','sensitivity','compare-development'))
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--vinay-root', type=Path, required=True)
    args = parser.parse_args()
    functions = {'fit-development': fit_development, 'sensitivity': sensitivity, 'compare-development': compare}
    functions[args.stage](args.handoff.resolve(), args.output.resolve(), args.vinay_root.resolve())


if __name__ == '__main__':
    main()
