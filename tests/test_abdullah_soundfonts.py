"""Check SoundFont subset selection and the acoustic comparison controls."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

import numpy as np

from workstreams.abdullah.compare_soundfonts import (
    FFT_SIZE,
    compare_pair,
    power_profile,
    run_comparison,
)
from workstreams.abdullah.fixtures import write_reference
from workstreams.abdullah.run import load_jobs, sha256


def write_tone(path: Path, frequency: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.sin(2 * np.pi * frequency * np.arange(8192) / 44100)
    stereo = np.column_stack((samples, samples))
    with wave.open(str(path), "wb") as audio:
        audio.setparams((2, 2, 44100, 0, "NONE", "not compressed"))
        audio.writeframes(np.rint(stereo * 10000).astype("<i2").tobytes())


def write_report(root: Path) -> Path:
    midi = write_reference(root / "source.mid")
    annotation = root / "annotation.json"
    annotation.write_text(json.dumps({"midi_path": midi.name}))
    rows = []
    for case in ("development_jazz", "development_rock"):
        for method in ("instrument_only", "fixed", "adaptive"):
            rows.append({
                "case_id": case,
                "method": method,
                "source_style": "jazz" if case.endswith("jazz") else "rock",
                "target_style": "rock" if case.endswith("jazz") else "jazz",
                "input_annotation": annotation.name,
                "annotation_sha256": sha256(annotation),
                "input_midi_sha256": sha256(midi),
                "output": midi.name,
                "output_sha256": sha256(midi),
            })
    report = root / "results.json"
    report.write_text(json.dumps({"runs": rows, "evidence_type": "test"}))
    return report


class SoundFontComparisonTests(unittest.TestCase):
    def test_subset_contains_all_four_conditions_and_rejects_invalid_selection(self):
        with TemporaryDirectory() as folder:
            report = write_report(Path(folder))
            jobs, _ = load_jobs(report, ["development_jazz"])
            self.assertEqual([job.method for job in jobs], ["source", "B0", "B1", "M"])
            self.assertEqual({job.case_id for job in jobs}, {"development_jazz"})
            all_jobs, _ = load_jobs(report)
            self.assertEqual(len(all_jobs), 8)
            for selected in ([], ["missing"], ["development_jazz", "development_jazz"]):
                with self.assertRaises(ValueError):
                    load_jobs(report, selected)

    def test_centroid_tracks_tone_frequency_and_normalization(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "tone.wav"
            frequency = 41 * 44100 / FFT_SIZE
            write_tone(path, frequency)
            profile, centroid = power_profile(path, 8192 / 44100)
            self.assertAlmostEqual(float(profile.sum()), 1)
            self.assertAlmostEqual(centroid, frequency, delta=1)
            write_tone(path, 2 * frequency)
            higher_profile, higher_centroid = power_profile(path, 8192 / 44100)
            self.assertAlmostEqual(higher_centroid, 2 * frequency, delta=1)
            self.assertGreater(float(np.abs(higher_profile - profile).sum() / 2), 0.99)
            with self.assertRaisesRegex(ValueError, "outside WAV bounds"):
                power_profile(path, 1)

    def test_silent_audio_is_rejected(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "silent.wav"
            write_tone(path, 0)
            with self.assertRaisesRegex(ValueError, "nonzero spectrum"):
                power_profile(path, 8192 / 44100)

    def test_pair_checks_hashes_duration_and_loudness_controls(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            rows = []
            for bank in ("baseline", "comparison"):
                path = root / bank / "tone.wav"
                write_tone(path, 41 * 44100 / FFT_SIZE)
                rows.append({
                    "case_id": "tone", "method": "M", "midi_sha256": "same-input",
                    "midi_duration_seconds": 8192 / 44100,
                    "audio": {"sample_rate_hz": 44100, "channels": 2, "frames": 8192},
                    "wav": "tone.wav", "wav_sha256": sha256(path),
                    "output_lufs": -23, "output_true_peak_dbtp": -10,
                    "loudness_matched": True,
                })
            metrics = compare_pair(root, *rows)
            self.assertEqual(metrics["normalized_spectrum_distance"], 0)
            self.assertEqual(metrics["centroid_change_hz"], 0)
            self.assertTrue(metrics["controls_passed"])
            rows[1]["loudness_matched"] = False
            self.assertFalse(compare_pair(root, *rows)["controls_passed"])
            rows[1]["audio"]["frames"] += 1
            with self.assertRaisesRegex(ValueError, "audio frames"):
                compare_pair(root, *rows)
            rows[1]["audio"]["frames"] -= 1
            rows[1]["wav_sha256"] = "changed"
            with self.assertRaisesRegex(ValueError, "WAV hash differs"):
                compare_pair(root, *rows)

    def test_same_soundfont_content_is_rejected_before_creating_output(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "first.sf2", root / "second.sf2"
            first.write_bytes(b"same soundfont")
            second.write_bytes(first.read_bytes())
            output = root / "output"
            args = argparse.Namespace(
                taimoor_results=write_report(root), case_ids=["development_jazz"],
                baseline_soundfont=first, comparison_soundfont=second, output=output,
            )
            with self.assertRaisesRegex(ValueError, "two different SoundFont"):
                run_comparison(args)
            self.assertFalse(output.exists())
