"""Compare two SoundFonts on identical source and B0/B1/M MIDI exports."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import sys
import wave

import numpy as np

from .render import SAMPLE_RATE, RenderError
from .run import load_jobs, render_batch, sha256


FFT_SIZE = 4096


def power_profile(path: Path, duration_seconds: float) -> tuple[np.ndarray, float]:
    """Summarize stereo power spectra over the MIDI interval, excluding its tail."""
    profile = np.zeros(FFT_SIZE // 2 + 1)
    window = np.hanning(FFT_SIZE)[:, None]
    with wave.open(str(path), "rb") as audio:
        rate = audio.getframerate()
        if (audio.getnchannels(), audio.getsampwidth()) != (2, 2):
            raise ValueError(f"Expected stereo PCM16: {path}")
        remaining = round(duration_seconds * rate)
        if not 0 < remaining <= audio.getnframes():
            raise ValueError(f"MIDI interval is outside WAV bounds: {path}")
        while remaining:
            count = min(remaining, FFT_SIZE)
            samples = np.frombuffer(audio.readframes(count), dtype="<i2")
            if len(samples) != count * 2:
                raise ValueError(f"Incomplete WAV frames: {path}")
            stereo = samples.reshape(-1, 2).astype(float) / 32768
            stereo = np.pad(stereo, ((0, FFT_SIZE - count), (0, 0)))
            power = np.abs(np.fft.rfft(stereo * window, axis=0)) ** 2
            profile += power.sum(axis=1)
            remaining -= count
    total = float(profile.sum())
    if not np.isfinite(total) or total <= 0:
        raise ValueError(f"No finite, nonzero spectrum in MIDI interval: {path}")
    profile /= total
    frequencies = np.fft.rfftfreq(FFT_SIZE, d=1 / rate)
    return profile, float(np.dot(frequencies, profile))


def compare_pair(output: Path, baseline: dict, comparison: dict) -> dict:
    """Check matching controls before measuring a SoundFont pair."""
    for key in ("case_id", "method", "midi_sha256", "midi_duration_seconds"):
        if baseline[key] != comparison[key]:
            raise ValueError(f"SoundFont pair differs in {key}")
    for key in ("sample_rate_hz", "channels", "frames"):
        if baseline["audio"][key] != comparison["audio"][key]:
            raise ValueError(f"SoundFont pair differs in audio {key}")
    profiles, centroids = [], []
    for bank, row in (("baseline", baseline), ("comparison", comparison)):
        path = output / bank / row["wav"]
        if sha256(path) != row["wav_sha256"]:
            raise ValueError(f"WAV hash differs from the render log: {path}")
        profile, centroid = power_profile(path, row["midi_duration_seconds"])
        profiles.append(profile)
        centroids.append(centroid)
    return {
        "baseline_centroid_hz": centroids[0],
        "comparison_centroid_hz": centroids[1],
        "centroid_change_hz": centroids[1] - centroids[0],
        "normalized_spectrum_distance": float(np.abs(profiles[1] - profiles[0]).sum() / 2),
        "loudness_change_lu": comparison["output_lufs"] - baseline["output_lufs"],
        "true_peak_change_db": comparison["output_true_peak_dbtp"] - baseline["output_true_peak_dbtp"],
        "controls_passed": baseline["loudness_matched"] and comparison["loudness_matched"],
    }


def write_summary(output: Path, report: dict) -> None:
    counts = report["totals"]
    lines = [
        "# SoundFont comparison for Objective 1 PI5", "",
        f"{counts['renders_passed']}/{counts['renders_attempted']} renders passed. "
        f"{counts['pairs_with_matched_controls']}/{counts['pairs_attempted']} pairs "
        "passed the matching, audio-format, duration, and loudness checks.", "",
        "The baseline bank and comparison bank use identical MIDI inputs, synthesis "
        "settings, duration alignment, and loudness targets. Bank details and hashes "
        "are in `comparison.json` and each bank's `results.json`.", "",
        "| Case | Direction | Method | Baseline centroid (Hz) | Comparison centroid (Hz) | "
        "Change (Hz) | Spectrum distance | Loudness change (LU) | Controls |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report["pairs"]:
        prefix = f"| {row['case_id']} | {row['direction']} | {row['method']} | "
        if row["status"] == "fail":
            lines.append(prefix + "- | - | - | - | - | fail |")
            continue
        lines.append(prefix + (
            f"{row['baseline_centroid_hz']:.1f} | {row['comparison_centroid_hz']:.1f} | "
            f"{row['centroid_change_hz']:+.1f} | {row['normalized_spectrum_distance']:.4f} | "
            f"{row['loudness_change_lu']:+.2f} | {row['controls_passed']} |"
        ))
    lines.extend([
        "", "## Measurement definitions", "",
        "Spectra use non-overlapping 4096-sample Hann windows, with a zero-padded "
        "final window. Squared FFT magnitudes from both stereo channels are summed over the "
        "MIDI interval. The half-second release tail is excluded. The aggregate "
        "power spectrum is normalized to sum to one. The centroid is its frequency-weighted "
        "mean in Hz. Spectrum distance is half the sum of absolute differences "
        "between the two normalized spectra, from zero to one. Changes are comparison "
        "minus baseline. These descriptors measure changes in the rendered sound.", "",
        "Synthesis and total processing times are recorded separately in each bank's "
        "render log. These are single-pass measurements including SoundFont loading.", "",
        "## Evidence scope", "",
        "Input evidence type: `" + report["evidence_type"] + "`. This comparison "
        "measures technical rendering consistency and acoustic sensitivity on the "
        "selected inputs. Genre preference, recognizability, and musical coherence "
        "require listener observations. No listener responses have been collected "
        "by this runner.", "",
    ])
    for row in report["pairs"]:
        if row["status"] == "fail":
            lines.append(f"- {row['case_id']}/{row['method']}: {row['error']}")
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    with (output / "paired_metrics.csv").open("w", newline="", encoding="utf-8") as file:
        columns = list(dict.fromkeys(key for row in report["pairs"] for key in row))
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(report["pairs"])


def run_comparison(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    jobs, evidence_type = load_jobs(args.taimoor_results.resolve(), args.case_ids)
    soundfonts = {
        "baseline": args.baseline_soundfont.resolve(),
        "comparison": args.comparison_soundfont.resolve(),
    }
    for path in soundfonts.values():
        if not path.is_file() or path.suffix.lower() != ".sf2":
            raise ValueError(f"Expected an existing .sf2 SoundFont: {path}")
    if len({sha256(path) for path in soundfonts.values()}) != 2:
        raise ValueError("The comparison requires two different SoundFont files")
    if output.exists():
        raise ValueError(f"Use a new output directory for each comparison: {output}")
    output.mkdir(parents=True)
    reports = {}
    for bank, path in soundfonts.items():
        options = argparse.Namespace(**{**vars(args), "soundfont": path, "output": output / bank})
        reports[bank] = render_batch(options, case_ids=args.case_ids, include_reference=False)
    rows_by_bank = {
        bank: {(row["case_id"], row["method"]): row for row in report["renders"]}
        for bank, report in reports.items()
    }
    pairs = []
    for job in jobs:
        row = {
            "case_id": job.case_id,
            "direction": f"{job.source_genre} to {job.target_genre}",
            "method": job.method,
            "midi_sha256": job.sha256,
        }
        baseline = rows_by_bank["baseline"][job.case_id, job.method]
        comparison = rows_by_bank["comparison"][job.case_id, job.method]
        try:
            for bank, item in (("baseline", baseline), ("comparison", comparison)):
                if item["status"] != "pass":
                    raise ValueError(f"{bank} rendering failed: {item['error']}")
                row[f"{bank}_wav"] = f"{bank}/{item['wav']}"
                row[f"{bank}_wav_sha256"] = item["wav_sha256"]
            row.update(compare_pair(output, baseline, comparison), status="pass")
        except (OSError, ValueError, wave.Error) as exc:
            row.update(status="fail", controls_passed=False, error=str(exc))
        pairs.append(row)
    report = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_type": evidence_type,
        "case_ids": sorted(args.case_ids),
        "numpy_version": version("numpy"),
        "soundfonts": {bank: bank_report["soundfont"] for bank, bank_report in reports.items()},
        "render_reports": {
            bank: {"path": f"{bank}/results.json", "sha256": sha256(output / bank / "results.json")}
            for bank in reports
        },
        "spectrum": {
            "fft_size": FFT_SIZE, "window": "Hann", "overlap": 0,
            "weighting": "squared magnitude", "include_release_tail": False,
        },
        "totals": {
            "renders_attempted": sum(report["totals"]["attempted"] for report in reports.values()),
            "renders_passed": sum(report["totals"]["passed"] for report in reports.values()),
            "pairs_attempted": len(jobs),
            "pairs_measured": sum(row["status"] == "pass" for row in pairs),
            "pairs_with_matched_controls": sum(row["controls_passed"] for row in pairs),
        },
        "pairs": pairs,
    }
    (output / "comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_summary(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taimoor-results", required=True, type=Path)
    parser.add_argument("--arranger-revision", help="Commit of the arranger results")
    parser.add_argument("--case-ids", nargs="+", required=True)
    parser.add_argument("--baseline-soundfont", type=Path, required=True)
    parser.add_argument("--comparison-soundfont", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("results/local/abdullah_soundfonts"))
    parser.add_argument("--sample-rate", type=int, default=SAMPLE_RATE)
    parser.add_argument("--fluidsynth", default="fluidsynth")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    try:
        report = run_comparison(args)
    except (RenderError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Cannot compare SoundFonts: {exc}", file=sys.stderr)
        return 1
    counts = report["totals"]
    print(f"{counts['pairs_with_matched_controls']}/{counts['pairs_attempted']} matched pairs. "
          f"Evidence: {args.output / 'summary.md'}")
    return int(counts["pairs_with_matched_controls"] != counts["pairs_attempted"])


if __name__ == "__main__":
    raise SystemExit(main())
