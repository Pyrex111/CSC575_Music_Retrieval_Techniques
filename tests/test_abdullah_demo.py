"""Check the MIDI upload contract and real playback assets for PI1/PI2."""

from io import BytesIO
from importlib.util import find_spec
import os
from pathlib import Path
import shutil
import unittest
import wave

import mido
from workstreams.abdullah.render import RenderError


HAS_DEMO_DEPENDENCIES = find_spec("pretty_midi") is not None
if HAS_DEMO_DEPENDENCIES:
    import pretty_midi
    from workstreams.abdullah.demo_backend import (
        MidiInputError, RendererSettings, load_midi, render_playback,
        validate_pair, validate_selection,
    )


FLUIDSYNTH = os.environ.get("CSC575_TEST_FLUIDSYNTH", "fluidsynth")
SOUNDFONT = Path(os.environ.get("CSC575_TEST_SOUNDFONT", "/usr/share/sounds/sf2/TimGM6mb.sf2"))


def midi_bytes(*, program=0, ticks=1920, channel=0, meter=(4, 4), file_type=1, tempo=500000):
    midi = mido.MidiFile(type=file_type, ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("track_name", name="Melody"),
        mido.MetaMessage("set_tempo", tempo=tempo),
        mido.MetaMessage("time_signature", numerator=meter[0], denominator=meter[1]),
        mido.Message("program_change", program=program, channel=channel),
        mido.Message("note_on", note=60, velocity=84, channel=channel),
        mido.Message("note_off", note=60, time=ticks, channel=channel),
    ]))
    output = BytesIO()
    midi.save(file=output)
    return output.getvalue()


@unittest.skipUnless(HAS_DEMO_DEPENDENCIES, "Requires the demonstration dependencies")
class MidiInterfaceTests(unittest.TestCase):
    def test_raw_download_bytes_and_backend_instrument_indices_are_preserved(self):
        data = midi_bytes()
        document = load_midi(data, "folder\\original.MIDI")
        backend = pretty_midi.PrettyMIDI(BytesIO(data))
        self.assertEqual(document.filename, "original.MIDI")
        self.assertEqual(document.data, data)
        self.assertEqual(document.duration_seconds, 2)
        self.assertEqual(document.tempo_bpm, 120)
        self.assertEqual(document.melody_indices, (0,))
        self.assertEqual(document.tracks[0].name, backend.instruments[0].name)
        self.assertEqual(document.tracks[0].note_count, len(backend.instruments[0].notes))
        self.assertTrue(document.tracks[0].label.startswith("0 · Melody"))

    def test_drum_instruments_are_visible_and_excluded_from_melody_choices(self):
        midi = mido.MidiFile(file=BytesIO(midi_bytes()))
        midi.tracks.append(mido.MidiTrack([
            mido.Message("note_on", note=36, velocity=80, channel=9),
            mido.Message("note_off", note=36, time=1920, channel=9),
        ]))
        stream = BytesIO()
        midi.save(file=stream)
        document = load_midi(stream.getvalue(), "with_drums.mid")
        drum = next(track for track in document.tracks if track.is_drum)
        self.assertNotIn(drum.index, document.melody_indices)
        self.assertEqual(len(document.tracks), 2)

    def test_malformed_and_unsupported_uploads_raise_clear_errors(self):
        for data, name in (
            (b"", "empty.mid"), (b"MThd\x00", "truncated.mid"),
            (midi_bytes(), "wrong.wav"), (midi_bytes(file_type=2), "async.mid"),
            (midi_bytes(channel=9), "drums.mid"), (midi_bytes(meter=(3, 4)), "waltz.mid"),
        ):
            with self.subTest(name=name):
                with self.assertRaises(MidiInputError):
                    load_midi(data, name)
        midi = mido.MidiFile(file=BytesIO(midi_bytes()))
        midi.tracks[0].insert(4, mido.MetaMessage("set_tempo", tempo=600000))
        stream = BytesIO()
        midi.save(file=stream)
        with self.assertRaisesRegex(MidiInputError, "constant-tempo"):
            load_midi(stream.getvalue(), "tempo_changes.mid")
        midi = mido.MidiFile(file=BytesIO(midi_bytes(tempo=600000)))
        midi.tracks[0][1].time = 480
        stream = BytesIO()
        midi.save(file=stream)
        with self.assertRaisesRegex(MidiInputError, "constant-tempo"):
            load_midi(stream.getvalue(), "late_tempo_change.mid")

    def test_pairing_rejects_different_excerpt_lengths_and_tempos(self):
        source = load_midi(midi_bytes(), "source.mid")
        validate_pair(source, load_midi(midi_bytes(program=32), "transformed.mid"))
        with self.assertRaisesRegex(MidiInputError, "same excerpt"):
            validate_pair(source, load_midi(midi_bytes(ticks=960), "short.mid"))
        # Matching wall-clock duration still requires the source tempo.
        with self.assertRaisesRegex(MidiInputError, "retain the source tempo"):
            validate_pair(source, load_midi(midi_bytes(tempo=1000000, ticks=960), "slower.mid"))

    def test_selection_requires_an_existing_pitched_track_and_supported_style(self):
        source = load_midi(midi_bytes(), "source.mid")
        validate_selection(source, 0, "jazz")
        validate_selection(source, 0, "rock")
        for index, style in ((-1, "jazz"), (1, "jazz"), (True, "jazz"), (0, "pop")):
            with self.subTest(index=index, style=style):
                with self.assertRaises(MidiInputError):
                    validate_selection(source, index, style)


@unittest.skipUnless(
    HAS_DEMO_DEPENDENCIES and SOUNDFONT.is_file() and shutil.which(FLUIDSYNTH) and shutil.which("ffmpeg"),
    "Requires FluidSynth, FFmpeg and CSC575_TEST_SOUNDFONT",
)
class PlaybackIntegrationTests(unittest.TestCase):
    def test_source_and_transformed_assets_are_complete_matched_wavs(self):
        source = load_midi(midi_bytes(), "source.mid")
        transformed = load_midi(midi_bytes(program=32), "transformed.mid")
        assets = render_playback(
            source, transformed, melody_track=0, target_style="jazz",
            settings=RendererSettings(SOUNDFONT, FLUIDSYNTH),
        )
        for data in (assets.source_wav, assets.transformed_wav):
            with wave.open(BytesIO(data), "rb") as audio:
                self.assertEqual((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()), (2, 2, 44100))
                self.assertEqual(audio.getnframes(), 110250)
                self.assertTrue(any(audio.readframes(audio.getnframes())))
        self.assertFalse(assets.peak_limited_outputs)

    def test_source_only_preview_and_missing_renderer(self):
        source = load_midi(midi_bytes(), "source.mid")
        assets = render_playback(
            source, None, melody_track=0, target_style="rock",
            settings=RendererSettings(SOUNDFONT, FLUIDSYNTH),
        )
        self.assertIsNotNone(assets.source_wav)
        self.assertIsNone(assets.transformed_wav)
        with self.assertRaisesRegex(RenderError, "Executable not found"):
            render_playback(
                source, None, melody_track=0, target_style="rock",
                settings=RendererSettings(SOUNDFONT, "csc575_missing_fluidsynth_executable"),
            )
