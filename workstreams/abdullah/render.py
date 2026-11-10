"""Render a MIDI file with FluidSynth and apply a documented loudness policy."""

from __future__ import annotations

import argparse
from array import array
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
import wave

from mido import MidiFile


SAMPLE_RATE = 44_100
SYNTH_GAIN = 0.2
TAIL_SECONDS = 0.5
FADE_SECONDS = 0.1
TARGET_LUFS = -23.0
TRUE_PEAK_CEILING_DBTP = -2.0
PEAK_MARGIN_DB = 0.1
LOUDNESS_TOLERANCE_LU = 0.25


class RenderError(RuntimeError):
    """A synthesis, loudness, or WAV validation failure."""


@dataclass(frozen=True)
class WavStats:
    sample_rate_hz: int
    channels: int
    frames: int
    duration_seconds: float
    peak_dbfs: float
    finite_samples: bool
    clipped_samples: int


@dataclass(frozen=True)
class RenderResult:
    output_path: Path
    midi_duration_seconds: float
    synthesized_duration_seconds: float
    synthesis_seconds: float
    elapsed_seconds: float
    audio: WavStats
    input_lufs: float
    input_true_peak_dbtp: float
    gain_db: float
    output_lufs: float
    output_true_peak_dbtp: float
    peak_limited: bool
    loudness_matched: bool


def run_command(arguments: list[str], timeout: float = 120) -> subprocess.CompletedProcess[str]:
    executable = Path(arguments[0]).name
    try:
        result = subprocess.run(
            arguments, capture_output=True, text=True, errors="replace", timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RenderError(f"Executable not found: {arguments[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"{executable} timed out after {timeout:g} seconds") from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RenderError(f"{executable} exited with status {result.returncode}: {detail}")
    return result


def inspect_wav(path: Path, sample_rate: int) -> WavStats:
    """Validate decoded, nonzero stereo PCM16 and measure its peak."""
    try:
        with wave.open(str(path), "rb") as wav:
            channels, width, rate, frames, _, _ = wav.getparams()
            if (channels, width, rate) != (2, 2, sample_rate):
                raise RenderError(f"Expected stereo PCM16 at {sample_rate} Hz: {path.name}")
            samples = array("h", wav.readframes(frames))
    except (wave.Error, EOFError, OSError, ValueError) as exc:
        raise RenderError(f"Cannot decode WAV {path.name}: {exc}") from exc
    if not frames or len(samples) != frames * channels:
        raise RenderError(f"WAV has empty or incomplete sample data: {path.name}")
    if sys.byteorder == "big":
        samples.byteswap()
    # The signed 16-bit PCM decoder admits only finite integer samples.
    low, high = min(samples), max(samples)
    peak = max(-low, high)
    if peak == 0:
        raise RenderError(f"WAV contains only silence: {path.name}")
    clipped = samples.count(-32768) + samples.count(32767) if peak >= 32767 else 0
    if clipped:
        raise RenderError(f"WAV has {clipped} full-scale samples: {path.name}")
    return WavStats(rate, channels, frames, frames / rate, 20 * math.log10(peak / 32768), True, clipped)


def measure_loudness(path: Path, ffmpeg: str) -> tuple[float, float]:
    result = run_command([
        ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-loglevel", "info",
        "-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-",
    ])
    try:
        start, end = result.stderr.rindex("{"), result.stderr.rindex("}")
        stats = json.loads(result.stderr[start:end + 1])
        integrated, true_peak = float(stats["input_i"]), float(stats["input_tp"])
    except (ValueError, KeyError, TypeError) as exc:
        raise RenderError(f"FFmpeg did not return loudness measurements for {path.name}") from exc
    if not all(math.isfinite(value) for value in (integrated, true_peak)):
        raise RenderError(f"Cannot measure finite loudness and true peak for {path.name}")
    return integrated, true_peak


def filter_pcm(source: Path, output: Path, filters: str, sample_rate: int, ffmpeg: str) -> None:
    run_command([
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(source),
        "-af", filters, "-c:a", "pcm_s16le", "-ar", str(sample_rate), "-ac", "2",
        "-map_metadata", "-1", str(output),
    ])


def render_midi(
    midi_path: str | Path,
    output_path: str | Path,
    soundfont_path: str | Path,
    *,
    sample_rate: int = SAMPLE_RATE,
    fluidsynth: str = "fluidsynth",
    ffmpeg: str = "ffmpeg",
) -> RenderResult:
    """Synthesize and validate one WAV before replacing the requested output."""
    midi, output, soundfont = (Path(p).resolve() for p in (midi_path, output_path, soundfont_path))
    if midi.suffix.lower() not in {".mid", ".midi"} or not midi.is_file():
        raise RenderError(f"Expected an existing .mid or .midi file: {midi}")
    with midi.open("rb") as source:
        if source.read(4) != b"MThd":
            raise RenderError(f"Invalid standard MIDI header: {midi.name}")
    if not soundfont.is_file() or soundfont.suffix.lower() != ".sf2":
        raise RenderError(f"Expected an existing .sf2 SoundFont: {soundfont}")
    if output.suffix.lower() != ".wav":
        raise RenderError(f"Output must have a .wav extension: {output}")
    if type(sample_rate) is not int or not 8000 <= sample_rate <= 96000:
        raise RenderError("Sample rate must be an integer between 8000 and 96000 Hz")
    try:
        midi_duration = MidiFile(midi).length
    except (OSError, EOFError, ValueError) as exc:
        raise RenderError(f"Cannot read MIDI duration for {midi.name}: {exc}") from exc
    if not math.isfinite(midi_duration) or midi_duration <= 0:
        raise RenderError(f"MIDI must have a positive duration: {midi.name}")
    frames = round((midi_duration + TAIL_SECONDS) * sample_rate)
    fade_frames = round(FADE_SECONDS * sample_rate)

    started = perf_counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".render-", dir=output.parent) as folder:
        raw = Path(folder) / "synth.wav"
        aligned = Path(folder) / "aligned.wav"
        staged = Path(folder) / "normalized.wav"
        config = Path(folder) / "empty.cfg"
        config.touch()
        synth_start = perf_counter()
        synthesis = run_command([
            fluidsynth, "-n", "-i", "-f", str(config), "-C", "0", "-R", "0",
            "-g", str(SYNTH_GAIN), "-r", str(sample_rate), "-T", "wav", "-O", "s16",
            "-F", str(raw), str(soundfont), str(midi),
        ])
        synthesis_seconds = perf_counter() - synth_start
        if "fluidsynth: error:" in synthesis.stderr.lower():
            raise RenderError(synthesis.stderr.strip())
        raw_stats = inspect_wav(raw, sample_rate)
        # Keep the complete MIDI interval and give every condition the same short tail.
        filter_pcm(
            raw, aligned, f"apad=whole_len={frames},atrim=end_sample={frames},"
            f"afade=t=out:ss={frames - fade_frames}:ns={fade_frames}", sample_rate, ffmpeg,
        )
        input_lufs, input_peak = measure_loudness(aligned, ffmpeg)

        desired_gain = TARGET_LUFS - input_lufs
        peak_safe_gain = TRUE_PEAK_CEILING_DBTP - PEAK_MARGIN_DB - input_peak
        gain = min(desired_gain, peak_safe_gain)
        filter_pcm(aligned, staged, f"volume={gain:.8f}dB:precision=double", sample_rate, ffmpeg)
        audio = inspect_wav(staged, sample_rate)
        output_lufs, output_peak = measure_loudness(staged, ffmpeg)
        if audio.frames != frames:
            raise RenderError(f"Expected {frames} aligned WAV frames, got {audio.frames}")
        if output_peak > TRUE_PEAK_CEILING_DBTP:
            raise RenderError(f"Normalized true peak exceeds {TRUE_PEAK_CEILING_DBTP:g} dBTP")
        os.replace(staged, output)

    return RenderResult(
        output, midi_duration, raw_stats.duration_seconds, synthesis_seconds, perf_counter() - started, audio,
        input_lufs, input_peak, gain, output_lufs, output_peak,
        gain < desired_gain, abs(output_lufs - TARGET_LUFS) <= LOUDNESS_TOLERANCE_LU,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("midi", type=Path)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--soundfont", type=Path, required=True)
    parser.add_argument("--sample-rate", type=int, default=SAMPLE_RATE)
    parser.add_argument("--fluidsynth", default="fluidsynth")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    try:
        result = render_midi(
            args.midi, args.wav, args.soundfont, sample_rate=args.sample_rate,
            fluidsynth=args.fluidsynth, ffmpeg=args.ffmpeg,
        )
    except (RenderError, OSError) as exc:
        print(f"Rendering failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
