"""Exercise real synthesis, matched WAV lengths, and safe failure handling."""

import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
import wave

from mido import Message, MidiFile, MidiTrack

from workstreams.abdullah.render import RenderError, render_midi


FLUIDSYNTH = os.environ.get("CSC575_TEST_FLUIDSYNTH", "fluidsynth")
SOUNDFONT = Path(os.environ.get("CSC575_TEST_SOUNDFONT", "/usr/share/sounds/sf2/TimGM6mb.sf2"))


def write_note(path: Path, program: int) -> None:
    midi = MidiFile(ticks_per_beat=480)
    midi.tracks.append(MidiTrack([
        Message("program_change", program=program),
        Message("note_on", note=60, velocity=84),
        Message("note_off", note=60, time=1920),
    ]))
    midi.save(path)


@unittest.skipUnless(
    SOUNDFONT.is_file() and shutil.which(FLUIDSYNTH) and shutil.which("ffmpeg"),
    "Requires FluidSynth, FFmpeg and CSC575_TEST_SOUNDFONT",
)
class RenderingIntegrationTests(unittest.TestCase):
    def test_presets_with_different_release_tails_produce_matched_lengths(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for program in (0, 32):
                midi, output = root / f"{program}.mid", root / f"{program}.wav"
                write_note(midi, program)
                rendered = render_midi(midi, output, SOUNDFONT, sample_rate=22050, fluidsynth=FLUIDSYNTH)
                with wave.open(str(output), "rb") as wav:
                    self.assertEqual(wav.getframerate(), 22050)
                    self.assertEqual(wav.getnframes(), 55125)
                self.assertTrue(rendered.loudness_matched)
                self.assertLessEqual(rendered.output_true_peak_dbtp, -2)

    def test_processing_failure_preserves_existing_output(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            midi, output = root / "input.mid", root / "existing.wav"
            write_note(midi, 0)
            with wave.open(str(output), "wb") as wav:
                wav.setparams((2, 2, 44100, 0, "NONE", "not compressed"))
                wav.writeframes(b"\x01\x00\x02\x00")
            original = output.read_bytes()
            with self.assertRaisesRegex(RenderError, "Executable not found"):
                render_midi(midi, output, SOUNDFONT, fluidsynth=FLUIDSYNTH, ffmpeg=str(root / "absent"))
            self.assertEqual(output.read_bytes(), original)
