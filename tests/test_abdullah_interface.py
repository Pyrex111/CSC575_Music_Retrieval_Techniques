"""Exercise the actual Streamlit entry point through its widget test harness."""

from importlib.util import find_spec
from io import BytesIO
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch
import wave

import mido

from test_abdullah_demo import FLUIDSYNTH, SOUNDFONT, midi_bytes


HAS_UI = find_spec("streamlit") is not None and find_spec("pretty_midi") is not None
if HAS_UI:
    from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "workstreams/abdullah/app.py"
HAS_AUDIO = SOUNDFONT.is_file() and shutil.which(FLUIDSYNTH) and shutil.which("ffmpeg")


@unittest.skipUnless(HAS_UI, "Requires the demonstration dependencies")
class InterfaceWidgetTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "CSC575_SOUNDFONT": str(SOUNDFONT),
            "CSC575_FLUIDSYNTH": FLUIDSYNTH,
            "CSC575_FFMPEG": "ffmpeg",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def app_with_source(self):
        app = AppTest.from_file(str(APP)).run(timeout=20)
        return app.file_uploader[0].set_value(("source.mid", midi_bytes(), "audio/midi")).run(timeout=20)

    def test_upload_validation_and_melody_and_style_choices(self):
        app = AppTest.from_file(str(APP)).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(app.info)
        app.file_uploader[0].set_value(("bad.mid", b"invalid file", "audio/midi")).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertIn("MIDI header", app.error[0].value)
        self.assertEqual(len(app.selectbox), 0)
        app.file_uploader[0].set_value(("source.mid", midi_bytes(), "audio/midi")).run(timeout=20)
        self.assertEqual(app.selectbox[0].value, 0)
        multiple = mido.MidiFile(file=BytesIO(midi_bytes()))
        multiple.tracks.append(mido.MidiTrack([
            mido.Message("program_change", channel=1, program=32),
            mido.Message("note_on", channel=1, note=48, velocity=84),
            mido.Message("note_off", channel=1, note=48, time=1920),
        ]))
        stream = BytesIO()
        multiple.save(file=stream)
        app.file_uploader[0].set_value(("multiple.mid", stream.getvalue(), "audio/midi")).run(timeout=20)
        app.selectbox[0].select(1).run(timeout=20)
        self.assertEqual(app.selectbox[0].value, 1)
        self.assertEqual(app.selectbox[1].options, ["Jazz", "Rock"])
        app.selectbox[1].select("Rock").run(timeout=20)
        self.assertEqual(app.selectbox[1].value, "Rock")
        downloads = app.get("download_button")
        self.assertFalse(downloads[0].disabled)
        self.assertTrue(downloads[1].disabled)
        self.assertTrue(downloads[2].disabled)
        self.assertTrue(downloads[3].disabled)

    def test_invalid_transformed_excerpt_disables_playback(self):
        app = self.app_with_source()
        app.file_uploader[1].set_value(("short.mid", midi_bytes(ticks=960), "audio/midi")).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertIn("same excerpt", app.error[0].value)
        self.assertTrue(app.button[0].disabled)
        self.assertEqual(len(app.get("audio")), 0)
        self.assertTrue(app.get("download_button")[2].disabled)

    @unittest.skipUnless(HAS_AUDIO, "Requires the synthesis tools and SoundFont")
    def test_real_playback_and_download_controls_for_both_target_styles(self):
        app = self.app_with_source()
        for style in ("Jazz", "Rock"):
            with self.subTest(style=style):
                app.selectbox[1].select(style).run(timeout=20)
                app.file_uploader[1].set_value(("transformed.mid", midi_bytes(program=32), "audio/midi")).run(timeout=20)
                app.button[0].click().run(timeout=30)
                self.assertFalse(app.exception)
                self.assertFalse(app.error)
                self.assertEqual(len(app.get("audio")), 2)
                self.assertTrue(all(not button.disabled for button in app.get("download_button")))
                self.assertTrue(all(button.proto.ignore_rerun for button in app.get("download_button")))
                assets = app.session_state["playback"]["assets"]
                for data in (assets.source_wav, assets.transformed_wav):
                    with wave.open(BytesIO(data), "rb") as audio:
                        self.assertEqual(audio.getframerate(), 44100)
                        self.assertEqual(audio.getnframes(), 110250)
                # A target change invalidates both the old output upload and audio.
                other = "Rock" if style == "Jazz" else "Jazz"
                app.selectbox[1].select(other).run(timeout=20)
                self.assertIsNone(app.file_uploader[1].value)
                self.assertEqual(len(app.get("audio")), 0)
                self.assertTrue(app.get("download_button")[3].disabled)

    @unittest.skipUnless(HAS_AUDIO, "Requires the synthesis tools and SoundFont")
    def test_source_and_renderer_changes_clear_old_preview_assets(self):
        app = self.app_with_source()
        app.button[0].click().run(timeout=30)
        self.assertEqual(len(app.get("audio")), 1)
        app.file_uploader[0].set_value(("new.mid", midi_bytes(program=32), "audio/midi")).run(timeout=20)
        self.assertEqual(len(app.get("audio")), 0)
        app.button[0].click().run(timeout=30)
        self.assertEqual(len(app.get("audio")), 1)
        app.sidebar.text_input[0].set_value("/missing/soundfont.sf2").run(timeout=20)
        self.assertEqual(len(app.get("audio")), 0)
        self.assertTrue(app.button[0].disabled)
        self.assertFalse(app.get("download_button")[0].disabled)

    @unittest.skipUnless(HAS_AUDIO, "Requires the synthesis tools and SoundFont")
    def test_renderer_errors_are_shown_without_stale_audio(self):
        app = self.app_with_source()
        # Python is executable, and rejects the FFmpeg-specific command arguments.
        app.sidebar.text_input[2].set_value(sys.executable).run(timeout=20)
        app.button[0].click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertIn("Playback could not be prepared", app.error[0].value)
        self.assertEqual(len(app.get("audio")), 0)
        self.assertTrue(app.get("download_button")[1].disabled)
