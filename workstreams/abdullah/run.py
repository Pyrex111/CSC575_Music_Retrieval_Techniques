"""Render the source and B0/B1/M MIDI exports and record validation evidence."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import re
import statistics
import sys
from time import perf_counter

from .fixtures import write_reference
from .render import (
    FADE_SECONDS,
    LOUDNESS_TOLERANCE_LU,
    PEAK_MARGIN_DB,
    SAMPLE_RATE,
    SYNTH_GAIN,
    TAIL_SECONDS,
    TARGET_LUFS,
    TRUE_PEAK_CEILING_DBTP,
    RenderError,
    render_midi,
    run_command,
)


METHODS = {"instrument_only": "B0", "fixed": "B1", "adaptive": "M"}
REFERENCE_ID = "abdullah_render_reference"


@dataclass(frozen=True)
class RenderJob:
    case_id: str
    source_genre: str
    target_genre: str
    method: str
    midi_path: Path
    sha256: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jobs(report_path: Path) -> tuple[list[RenderJob], str]:
    root = report_path.parent
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cases: dict[str, dict[str, RenderJob]] = {}
    annotations: dict[str, Path] = {}
    for row in report["runs"]:
        method = METHODS.get(row["method"])
        if method is None:
            continue
        case_id = row["case_id"]
        source, target = row["source_style"], row["target_style"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", case_id) or case_id == REFERENCE_ID:
            raise ValueError(f"Invalid or reserved case ID: {case_id!r}")
        if {source, target} != {"jazz", "rock"}:
            raise ValueError(f"Expected Jazz/Rock transfer for {case_id}")
        annotation = (root / row["input_annotation"]).resolve()
        if case_id not in cases:
            if sha256(annotation) != row["annotation_sha256"]:
                raise ValueError(f"Annotation hash differs from the arranger report for {case_id}")
            source_data = json.loads(annotation.read_text(encoding="utf-8"))
            source_midi = (annotation.parent / source_data["midi_path"]).resolve()
            cases[case_id] = {"source": RenderJob(
                case_id, source, target, "source", source_midi, row["input_midi_sha256"],
            )}
            annotations[case_id] = annotation
        case = cases[case_id]
        reference = case["source"]
        if (reference.source_genre, reference.target_genre, reference.sha256, annotations[case_id]) != (
            source, target, row["input_midi_sha256"], annotation,
        ):
            raise ValueError(f"Comparison conditions use different inputs for {case_id}")
        if method in case:
            raise ValueError(f"Duplicate {method} export for {case_id}")
        case[method] = RenderJob(
            case_id, source, target, method, (root / row["output"]).resolve(), row["output_sha256"],
        )
    if not cases:
        raise ValueError("Arranger report contains no comparison cases")
    order = ("source", *METHODS.values())
    for case_id, case in cases.items():
        missing = set(order) - case.keys()
        if missing:
            raise ValueError(f"Missing conditions for {case_id}: {', '.join(sorted(missing))}")
    jobs = [case[method] for _, case in sorted(cases.items()) for method in order]
    return jobs, report["evidence_type"]


def write_listening_manifest(output: Path, rows: list[dict]) -> None:
    passed = {(row["case_id"], row["method"]): row for row in rows if row["status"] == "pass"}
    case_ids = sorted({row["case_id"] for row in rows if row["target_genre"]})
    columns = ("composition_id", "target_genre", "method", "audio_path", "source_audio_path")
    with (output / "listening_manifest.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for case_id in case_ids:
            if not all((case_id, method) in passed for method in ("source", *METHODS.values())):
                continue
            for method in METHODS.values():
                row = passed[case_id, method]
                writer.writerow({
                    "composition_id": case_id,
                    "target_genre": row["target_genre"],
                    "method": method,
                    "audio_path": row["wav"],
                    "source_audio_path": passed[case_id, "source"]["wav"],
                })


def write_summary(output: Path, report: dict) -> None:
    totals = report["totals"]
    lines = [
        "# Rendering validation results", "",
        f"{totals['passed']}/{totals['attempted']} renders passed. "
        f"{totals['reference_passed']} source references and "
        f"{totals['comparison_passed']} comparison WAVs passed.", "",
        "| Case | Direction | Method | WAV length (s) | Synthesis (s) | Total (s) | LUFS | dBTP | Status |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report["renders"]:
        direction = f"{row['source_genre']} to {row['target_genre']}" if row["target_genre"] else "Reference"
        fields = f"| {row['case_id']} | {direction} | {row['method']} | "
        if row["status"] == "fail":
            lines.append(fields + "— | — | — | — | — | fail |")
            continue
        lines.append(fields + (
            f"{row['audio']['duration_seconds']:.2f} | {row['synthesis_seconds']:.3f} | "
            f"{row['elapsed_seconds']:.3f} | {row['output_lufs']:.2f} | "
            f"{row['output_true_peak_dbtp']:.2f} | pass |"
        ))
    failures = [row for row in report["renders"] if row["status"] == "fail"]
    if failures:
        lines.extend(["", "## Failures", ""])
        for row in failures:
            detail = " ".join(row["error"].splitlines())
            lines.append(f"- {row['case_id']}/{row['method']}: {detail}")
    lines.extend(["", "Synthesis time covers FluidSynth. Total time includes loudness processing and WAV checks.", ""])
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def render_batch(args: argparse.Namespace) -> dict:
    input_report = args.taimoor_results.resolve()
    jobs, evidence_type = load_jobs(input_report)
    output = args.output.resolve()
    soundfont = args.soundfont.resolve()
    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "mido": version("mido"),
        "fluidsynth": run_command([args.fluidsynth, "-V"]).stdout.strip(),
        "ffmpeg": run_command([args.ffmpeg, "-version"]).stdout.splitlines()[0],
    }
    soundfont_metadata = {"filename": soundfont.name, "sha256": sha256(soundfont)}
    if output.exists():
        raise ValueError(f"Use a new output directory for each validation run: {output}")
    output.mkdir(parents=True)
    reference = write_reference(output / "fixtures" / f"{REFERENCE_ID}.mid")
    jobs.append(RenderJob(REFERENCE_ID, "", "", "source", reference, sha256(reference)))
    rows = []
    source_frames = {}
    for job in jobs:
        wav = Path("audio") / job.case_id / f"{job.method}.wav"
        row = {
            "case_id": job.case_id,
            "source_genre": job.source_genre,
            "target_genre": job.target_genre,
            "method": job.method,
            "midi_filename": job.midi_path.name,
            "midi_sha256": job.sha256,
        }
        started = perf_counter()
        try:
            if sha256(job.midi_path) != job.sha256:
                raise RenderError("MIDI hash differs from the recorded input or arrangement export")
            rendered = render_midi(
                job.midi_path, output / wav, soundfont, sample_rate=args.sample_rate,
                fluidsynth=args.fluidsynth, ffmpeg=args.ffmpeg,
            )
            if job.method == "source":
                source_frames[job.case_id] = rendered.audio.frames
            elif job.case_id in source_frames and rendered.audio.frames != source_frames[job.case_id]:
                raise RenderError("Comparison WAV length differs from the matched source WAV")
            metrics = asdict(rendered)
            del metrics["output_path"]
            row.update(metrics, status="pass", wav=wav.as_posix(), wav_sha256=sha256(output / wav))
        except (RenderError, OSError) as exc:
            row.update(status="fail", error=str(exc), elapsed_seconds=perf_counter() - started)
        rows.append(row)
        print(f"{job.case_id}/{job.method}: {row['status']}", flush=True)

    passed = [row for row in rows if row["status"] == "pass"]
    synth_times = [row["synthesis_seconds"] for row in passed]
    reference_count = sum(row["method"] == "source" for row in passed)
    report = {
        "schema_version": 1,
        "environment": environment,
        "soundfont": soundfont_metadata,
        "arranger_report": {
            "revision": args.arranger_revision,
            "sha256": sha256(input_report),
            "evidence_type": evidence_type,
        },
        "code_sha256": {file.name: sha256(file) for file in sorted(Path(__file__).parent.glob("*.py"))},
        "settings": {
            "sample_rate_hz": args.sample_rate,
            "wav_encoding": "stereo PCM16",
            "synth_gain": SYNTH_GAIN,
            "chorus": False,
            "reverb": False,
            "post_midi_tail_seconds": TAIL_SECONDS,
            "tail_fade_seconds": FADE_SECONDS,
            "target_lufs": TARGET_LUFS,
            "true_peak_ceiling_dbtp": TRUE_PEAK_CEILING_DBTP,
            "peak_margin_db": PEAK_MARGIN_DB,
            "loudness_tolerance_lu": LOUDNESS_TOLERANCE_LU,
        },
        "totals": {
            "attempted": len(rows), "passed": len(passed), "failed": len(rows) - len(passed),
            "reference_passed": reference_count, "comparison_passed": len(passed) - reference_count,
            "peak_limited": sum(row["peak_limited"] for row in passed),
            "outside_loudness_tolerance": sum(not row["loudness_matched"] for row in passed),
            "median_synthesis_seconds": statistics.median(synth_times) if synth_times else None,
            "synthesis_seconds_total": sum(synth_times),
            "elapsed_seconds_total": sum(row["elapsed_seconds"] for row in rows),
        },
        "renders": rows,
    }
    (output / "results.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_summary(output, report)
    write_listening_manifest(output, rows)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taimoor-results", required=True, type=Path)
    parser.add_argument("--arranger-revision", help="Commit of the arranger results for the evidence record")
    parser.add_argument("--soundfont", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/local/abdullah"))
    parser.add_argument("--sample-rate", type=int, default=SAMPLE_RATE)
    parser.add_argument("--fluidsynth", default="fluidsynth")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    try:
        report = render_batch(args)
    except (RenderError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Cannot run rendering validation: {exc}", file=sys.stderr)
        return 1
    counts = report["totals"]
    print(f"{counts['passed']}/{counts['attempted']} WAVs passed. Evidence: {args.output / 'summary.md'}")
    return int(counts["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
