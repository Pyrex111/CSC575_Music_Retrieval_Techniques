"""MIDI loading and playback assets for the PI1/PI2 demonstration interface."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import math
from pathlib import Path
import struct
from tempfile import TemporaryDirectory

import mido
import pretty_midi

from .render import SAMPLE_RATE, RenderError, render_midi


class MidiInputError(ValueError):
    """A MIDI upload is malformed or outside the supported input contract."""


@dataclass(frozen=True)
class MidiTrack:
    index: int
    name: str
    program: int
    is_drum: bool
    note_count: int

    @property
    def label(self) -> str:
        instrument = "Drums" if self.is_drum else pretty_midi.program_to_instrument_name(self.program)
        return f"{self.index} · {self.name or instrument} · {self.note_count} notes"


@dataclass(frozen=True)
class MidiDocument:
    filename: str
    data: bytes
    sha256: str
    duration_seconds: float
    tempo_bpm: float
    ticks_per_beat: int
    tracks: tuple[MidiTrack, ...]

    @property
    def melody_indices(self) -> tuple[int, ...]:
        return tuple(track.index for track in self.tracks if not track.is_drum and track.note_count)


@dataclass(frozen=True)
class RendererSettings:
    soundfont: Path
    fluidsynth: str = "fluidsynth"
    ffmpeg: str = "ffmpeg"

    def identity(self) -> tuple:
        path = self.soundfont.expanduser().resolve()
        stamp = (path.stat().st_size, path.stat().st_mtime_ns) if path.is_file() else None
        return str(path), stamp, self.fluidsynth, self.ffmpeg


@dataclass(frozen=True)
class PlaybackAssets:
    source_wav: bytes
    transformed_wav: bytes | None
    peak_limited_outputs: tuple[str, ...]


def load_midi(data: bytes, filename: str) -> MidiDocument:
    """Expose PrettyMIDI instrument indices, matching the arranger's melody contract."""
    filename = Path(filename.replace("\\", "/")).name
    if Path(filename).suffix.lower() not in {".mid", ".midi"}:
        raise MidiInputError("Choose a .mid or .midi file.")
    if not data.startswith(b"MThd"):
        raise MidiInputError("The file has no valid standard MIDI header.")
    try:
        raw = mido.MidiFile(file=BytesIO(data))
        if raw.type not in (0, 1):
            raise MidiInputError("Use a synchronous type-0 or type-1 MIDI file.")
        if raw.ticks_per_beat <= 0:
            raise MidiInputError("Use beat-based MIDI timing. SMPTE timing is unsupported.")
        tempos = set()
        current_tempo = 500000
        for message in mido.merge_tracks(raw.tracks):
            if message.time:
                tempos.add(current_tempo)
            if message.type == "set_tempo":
                current_tempo = message.tempo
                tempos.add(current_tempo)
        if len(tempos) > 1:
            raise MidiInputError("This interface supports constant-tempo excerpts. Crop tempo changes first.")
        tempo = next(iter(tempos), 500000)
        if tempo <= 0:
            raise MidiInputError("The MIDI tempo must be positive.")
        if any(message.numerator != 4 or message.denominator != 4 for track in raw.tracks
               for message in track if message.type == "time_signature"):
            raise MidiInputError("This project supports excerpts in 4/4 time.")
        duration = raw.length
        if not math.isfinite(duration) or duration <= 0:
            raise MidiInputError("The MIDI excerpt must have a positive, finite duration.")
        parsed = pretty_midi.PrettyMIDI(BytesIO(data))
    except MidiInputError:
        raise
    except (EOFError, OSError, ValueError, TypeError, IndexError, KeyError, struct.error) as exc:
        raise MidiInputError("The MIDI file could not be read. Check that it is complete and valid.") from exc
    tracks = tuple(
        MidiTrack(index, instrument.name, instrument.program, instrument.is_drum, len(instrument.notes))
        for index, instrument in enumerate(parsed.instruments)
    )
    document = MidiDocument(
        filename, data, hashlib.sha256(data).hexdigest(), duration,
        mido.tempo2bpm(tempo), raw.ticks_per_beat, tracks,
    )
    if not document.melody_indices:
        raise MidiInputError("The MIDI needs at least one nonempty pitched track for melody selection.")
    return document


def validate_selection(source: MidiDocument, melody_track: int, target_style: str) -> None:
    if type(melody_track) is not int or melody_track not in source.melody_indices:
        raise MidiInputError("Select a nonempty pitched melody track from the source MIDI.")
    if target_style not in {"jazz", "rock"}:
        raise MidiInputError("Choose Jazz or Rock as the target style.")


def validate_pair(source: MidiDocument, transformed: MidiDocument) -> None:
    tolerance = max(
        60 / source.tempo_bpm / source.ticks_per_beat,
        60 / transformed.tempo_bpm / transformed.ticks_per_beat,
    )
    if abs(source.duration_seconds - transformed.duration_seconds) > tolerance + 1e-9:
        raise MidiInputError("The transformed MIDI must cover the same excerpt as the source.")
    if abs(source.tempo_bpm - transformed.tempo_bpm) > 0.001:
        raise MidiInputError("The transformed MIDI must retain the source tempo.")


def render_playback(
    source: MidiDocument,
    transformed: MidiDocument | None,
    *,
    melody_track: int,
    target_style: str,
    settings: RendererSettings,
) -> PlaybackAssets:
    """Render supplied backend MIDI exports through the existing render_midi API."""
    validate_selection(source, melody_track, target_style)
    if transformed is not None:
        validate_pair(source, transformed)
    waves: dict[str, bytes] = {}
    limited = []
    with TemporaryDirectory(prefix="csc575-playback-") as folder:
        root = Path(folder)
        for role, document in (("source", source), ("transformed", transformed)):
            if document is None:
                continue
            midi, output = root / f"{role}.mid", root / f"{role}.wav"
            midi.write_bytes(document.data)
            rendered = render_midi(
                midi, output, settings.soundfont.expanduser(), sample_rate=SAMPLE_RATE,
                fluidsynth=settings.fluidsynth, ffmpeg=settings.ffmpeg,
            )
            waves[role] = output.read_bytes()
            if not rendered.loudness_matched:
                if not rendered.peak_limited:
                    raise RenderError(f"The {role} preview did not meet the loudness target")
                limited.append(role)
    return PlaybackAssets(waves["source"], waves.get("transformed"), tuple(limited))
