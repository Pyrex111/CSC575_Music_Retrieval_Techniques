"""Run from repo root: python -m workstreams.taimoor.run --output results/local."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import time

from .arranger import Weights, arrange
from .evaluate import measure
from .fixtures import make_fixtures
from .model import load_song, write_midi


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plot(song, midi, path: Path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    fig, axes = plt.subplots(2, 1, figsize=(11, 5), sharex=True, sharey=True)
    for ax, data, title in zip(axes, (song.midi, midi), ('Source fixture', 'Adaptive arrangement')):
        melody_index = song.melody_track if data is song.midi else 0
        for index, instrument in enumerate(data.instruments):
            if instrument.is_drum:
                continue
            segments = [[(n.start/song.seconds_per_beat, n.pitch), (n.end/song.seconds_per_beat, n.pitch)]
                        for n in instrument.notes]
            ax.add_collection(LineCollection(segments, colors='#0057b8' if index == melody_index else '#c47525',
                                            linewidths=2, alpha=0.9 if index == melody_index else 0.5))
        for phrase in song.phrases:
            ax.axvline(phrase.start_bar*4, color='gray', lw=0.6)
        ax.set_ylabel('MIDI pitch'); ax.set_title(title); ax.set_ylim(34, 100)
    axes[-1].set_xlim(0, song.duration_beats); axes[-1].set_xlabel('Beats')
    fig.suptitle(f'{song.case_id}: {song.source_style} to {"jazz" if song.source_style == "rock" else "rock"}\n'
                 'Blue: protected melody; orange: pitched accompaniment. Synthetic engineering example.')
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('results/local/taimoor'))
    parser.add_argument('--annotation', type=Path, help='Use a reviewed local excerpt instead of generated fixtures')
    parser.add_argument('--style-weight', type=float, default=1.0)
    parser.add_argument('--continuity-weight', type=float, default=0.8)
    parser.add_argument('--plots', action='store_true', help='Create one piano-roll comparison per input')
    args = parser.parse_args(argv)
    weights = Weights(args.style_weight, args.continuity_weight)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    annotations = [args.annotation] if args.annotation else make_fixtures(output/'fixtures')
    git = subprocess.run(['git', 'rev-parse', 'HEAD'], text=True, capture_output=True)
    dirty = subprocess.run(['git', 'status', '--porcelain'], text=True, capture_output=True)
    source_files = sorted(Path(__file__).parent.glob('*.py'))
    code_hashes = {p.name: sha256(p) for p in source_files}
    report = {
        'evidence_type': 'synthetic_engineering_checks' if not args.annotation else 'user_supplied_excerpt',
        'limitations': ['No real-song held-out evaluation or listening study has been completed.',
                        'Hand-authored templates and weights; no trained model or genre-quality claim.',
                        'Reference baselines here are test comparators, not Smit\u2019s completed contribution.'],
        'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                        'pretty_midi': version('pretty_midi'), 'mido': version('mido')},
        'code': {'git_head': git.stdout.strip() if git.returncode == 0 else None,
                 'working_tree_dirty': bool(dirty.stdout.strip()), 'sha256': code_hashes},
        'weights': asdict(weights), 'random_seed': None, 'deterministic': True, 'runs': [],
    }
    failures = []
    for annotation in annotations:
        song = load_song(annotation)
        target = 'jazz' if song.source_style == 'rock' else 'rock'
        folder = output/song.case_id
        folder.mkdir(exist_ok=True)
        condition_results = {}
        for method in ('instrument_only', 'fixed', 'adaptive', 'no_continuity'):
            started = time.perf_counter()
            transformed, trace = arrange(song, target, method, weights)
            transform_seconds = time.perf_counter()-started
            midi_path = folder/f'{method}.mid'
            write_midi(transformed, midi_path, song.duration_beats, song.phrases)
            metrics, signature = measure(song, midi_path, trace['melody_track'])
            condition_results[method] = (metrics, signature, trace)
            row = {'case_id': song.case_id, 'split': song.split, 'source_style': song.source_style,
                   'target_style': target, 'method': method, 'transform_seconds': transform_seconds,
                   'output': midi_path.relative_to(output).as_posix(), 'output_sha256': sha256(midi_path),
                   'input_midi_sha256': sha256(song.midi_path), 'annotation_sha256': sha256(song.annotation_path),
                   'input_annotation': str(song.annotation_path.relative_to(output)) if not args.annotation else str(song.annotation_path),
                   'chords': [{'root_pc': c.root_pc, 'intervals': c.intervals} for c in song.chords],
                   'metrics': metrics, 'trace': trace}
            row['generated_harmony_register_constraints_applicable'] = method != 'instrument_only'
            report['runs'].append(row)
            if not all(metrics[k] for k in ('melody_preserved', 'duration_preserved', 'phrase_markers_preserved',
                                            'tempo_preserved', 'time_signature_preserved')):
                failures.append(f'{song.case_id}/{method}: invariant failure')
            if metrics['event_bounds_violations'] or (method != 'instrument_only' and (
                    metrics['register_violations'] or metrics['harmony_pitch_class_violations'])):
                failures.append(f'{song.case_id}/{method}: invalid accompaniment')
            if method == 'adaptive' and args.plots:
                plot(song, transformed, folder/'piano_roll.png')
        fixed_signature = condition_results['fixed'][1]
        for row in report['runs'][-4:]:
            signature = condition_results[row['method']][1]
            row['accompaniment_event_difference_from_fixed'] = sum((signature-fixed_signature).values()) + sum((fixed_signature-signature).values())
    (output/'results.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    lines = ['# Arrangement engineering results', '',
             report['evidence_type'] + '. These checks do not establish perceptual genre quality.',
             'Instrument-only chord/register counts describe retained source notes; generator-specific constraints do not apply to B0.', '',
             '| Input | Direction | Method | Melody / duration / markers | Harmony / register / bounds violations | Events different from fixed | Transformation seconds |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for row in report['runs']:
        m = row['metrics']
        check = 'pass' if all(m[k] for k in ('melody_preserved', 'duration_preserved', 'phrase_markers_preserved')) else 'FAIL'
        lines.append(f'| {row["case_id"]} | {row["source_style"]} to {row["target_style"]} | {row["method"]} | {check} | '
                     f'{m["harmony_pitch_class_violations"]} / {m["register_violations"]} / {m["event_bounds_violations"]} | '
                     f'{row["accompaniment_event_difference_from_fixed"]} | {row["transform_seconds"]:.5f} |')
    (output/'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(f'{len(report["runs"])} runs; {len(failures)} invariant/validity failures; results: {output}')
    if failures:
        raise SystemExit('\n'.join(failures))


if __name__ == '__main__':
    main()
