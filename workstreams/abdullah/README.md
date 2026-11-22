# Abdullah’s MIDI-to-WAV rendering workstream

This workstream implements Objective 1 through PI5 on the documented synthetic demonstration set. It renders MIDI exports with FluidSynth, applies the same loudness procedure to each file, and records WAV validation and timing. The PI5 runner compares two SoundFonts on matched inputs. The [progress record](../../docs/abdullah_progress.md) describes the inputs and measured results.

## Setup

Use Python 3.10 or newer, FluidSynth with WAV output support, FFmpeg, and a General MIDI `.sf2` SoundFont. The workstream uses `mido` to read the MIDI duration and generate its fifth reference MIDI.

On Ubuntu 24.04:

```bash
sudo apt update
sudo apt install fluidsynth ffmpeg timgm6mb-soundfont
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r workstreams/abdullah/requirements.txt
fluidsynth -V
ffmpeg -version
sha256sum /usr/share/sounds/sf2/TimGM6mb.sf2
```

On other platforms, install FluidSynth and FFmpeg for your OS and supply the SoundFont path. The commands accept `--fluidsynth` and `--ffmpeg` if the executables are outside `PATH`. [FluidSynth manual](https://www.fluidsynth.org/wiki/UserManual/) · [FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html#loudnorm)

| Component | Recorded version and provenance |
| --- | --- |
| FluidSynth | Executable and runtime **2.3.4**, Ubuntu package `2.3.4-1build3`. The package lists LGPL-2.1-or-later for the main code, with per-file terms in `/usr/share/doc/fluidsynth/copyright`. [Ubuntu package](https://packages.ubuntu.com/noble/fluidsynth) |
| SoundFont | `TimGM6mb.sf2`, Ubuntu `timgm6mb-soundfont` **1.3-5**. The package copyright file attributes the SoundFont to Tim Brechbill and David Bolton and specifies GPL version 2 for the `.sf2`. [Exact Ubuntu package](https://snapshot.ubuntu.com/ubuntu/20260828T000000Z/pool/universe/t/timgm6mb-soundfont/timgm6mb-soundfont_1.3-5_all.deb) · [Upstream source identified in the package](https://github.com/musescore/musescore-old/commit/90c33ef9d87b3f5ff92efd3b07d89eb455fb1fef) |
| FFmpeg | `6.1.1-3ubuntu5` for loudness measurement and PCM gain adjustment. [Recorded environment](../../results/abdullah_progress/results.json) |

The tested SoundFont SHA-256 is `c5378b62028c920cb11e4803327983fee2f2cdff5dc89c708e39da417e51c854`. Install the SoundFont separately. Its package notice is available in `/usr/share/doc/timgm6mb-soundfont/copyright`.

## Render a single file

```bash
python -m workstreams.abdullah.render input.mid results/local/example.wav \
  --soundfont /usr/share/sounds/sf2/TimGM6mb.sf2 \
  --sample-rate 44100
```

The corresponding Python interface is `render_midi(midi_path, output_path, soundfont_path, sample_rate=44100)`. It returns the output path, synthesis and total times, WAV information, and measured loudness. The WAV is decoded and checked for the requested sample rate, stereo PCM16, complete frames, nonzero samples, and clipping. The PCM16 sample format represents finite integers. External process failures include a captured diagnostic. A failed attempt leaves an existing destination file intact.

## Reproduce the comparison batch

Fetch the snapshot of Taimoor’s branch that supplied the recorded MIDI exports and check it out in a separate worktree.

```bash
git fetch origin taimoor/arranger-progress
git worktree add --detach ../csc575-arranger-fixtures 387769d6ebdc44770535b0b6b42cf6d4e2bf85a3

python -m workstreams.abdullah.run \
  --taimoor-results ../csc575-arranger-fixtures/results/taimoor_progress/results.json \
  --arranger-revision 387769d6ebdc44770535b0b6b42cf6d4e2bf85a3 \
  --soundfont /usr/share/sounds/sf2/TimGM6mb.sf2 \
  --sample-rate 44100 \
  --output results/local/abdullah
```

Use a new output directory for each run. The batch consumes the saved MIDI exports and verifies their hashes and associated annotation hashes against Taimoor’s report. It maps `instrument_only` to B0, `fixed` to B1, and `adaptive` to M. For each case it renders the source and all three comparisons. It also writes and renders an original 16-bar reference fixture at 96 BPM. [Arranger snapshot](https://github.com/Pyrex111/CSC575_Music_Retrieval_Techniques/tree/387769d6ebdc44770535b0b6b42cf6d4e2bf85a3/results/taimoor_progress)

The output directory contains playable WAVs under `audio/`, a generated reference MIDI under `fixtures/`, a `summary.md` timing table, and `results.json` with per-file settings, checksums, failures, and measurements. The listening manifest maps each B0/B1/M WAV to its source WAV. Paths in that CSV are relative to the run directory. The generated audio stays in `results/local/` and can be recreated from the pinned inputs. The committed evidence is in [`results/abdullah_progress`](../../results/abdullah_progress).

## Rendering and loudness procedure

1. Synthesize all files with the same SoundFont, 44,100 Hz sample rate, stereo PCM16 output, gain `0.2`, and chorus and reverb disabled. FluidSynth uses an empty command configuration for each invocation.
2. Align each WAV to the MIDI endpoint plus **0.5 seconds** of release tail. Trim or pad the tail to that frame count and fade its final **0.1 seconds**. The batch checks that all WAVs within a matched case have equal lengths.
3. Measure the aligned WAV's integrated loudness and true peak using FFmpeg's `loudnorm` analysis. Target **−23 LUFS** with a **−2 dBTP** ceiling and a **0.1 dB** allowance for measurement rounding and PCM conversion.
4. Apply a constant gain in dB. The gain is the smaller of `−23 − measured LUFS` and `−2.1 − measured dBTP`. This preserves the waveform's dynamics and lets peak-constrained files remain quieter. The report identifies any such file.
5. Decode the result again and remeasure loudness and true peak. If loudness is outside **0.25 LU** of the target, correct the constant gain using the remaining peak headroom and remeasure, with at most three passes. Each pass starts from the aligned audio. Record the pass count and any peak limitation. A failure to reach the target without a peak limitation returns an error before replacing the destination. Check the final frame count and true-peak ceiling.

Synthesis time measures the FluidSynth command. Total rendering time also includes length alignment, loudness analysis, gain adjustment, and validation. These are separate from the arrangers’ transformation times. [FFmpeg audio filters](https://ffmpeg.org/ffmpeg-filters.html#Audio-Filters)

## Compare a second SoundFont for PI5

Install the dependencies above and the FluidR3 General MIDI bank. The recorded comparison uses `fluid-soundfont-gm` version `3.1-5.3`, whose SoundFont has an MIT notice. The package versions, file hashes, source URLs, and notices are retained in the [SoundFont provenance record](../../results/abdullah_soundfont_comparison/soundfont_provenance.json).

```bash
sudo apt install fluid-soundfont-gm
python -m workstreams.abdullah.compare_soundfonts \
  --taimoor-results ../csc575-arranger-fixtures/results/taimoor_progress/results.json \
  --arranger-revision 387769d6ebdc44770535b0b6b42cf6d4e2bf85a3 \
  --case-ids development_jazz development_rock \
  --baseline-soundfont /usr/share/sounds/sf2/TimGM6mb.sf2 \
  --comparison-soundfont /usr/share/sounds/sf2/FluidR3_GM.sf2 \
  --output results/local/abdullah_soundfonts
```

Use the pinned arranger worktree from the preceding instructions. The runner reuses `render_midi` and the original batch procedure, selects the requested cases, and renders source/B0/B1/M under both banks. The extra fifth reference belongs to the original PI1-PI4 run and is excluded from this matched subset. The comparison rejects repeated or unknown case IDs and identical SoundFont contents. The default batch command above retains its original full-set behavior.

Each bank's output folder contains eight WAVs, a `results.json` render log, and a `listening_manifest.csv` compatible with the existing evaluation loader. Manifest audio paths are relative to that bank's folder. The comparison root contains `comparison.json`, `paired_metrics.csv`, and `summary.md`. Failed renders remain in the logs and denominator. A nonzero exit status indicates a failed pair or an unmet loudness control.

The acoustic measures use normalized aggregate power spectra with 4096-sample Hann windows over the MIDI interval. The summary defines the centroid and spectral distance. The measurements and [interpretation](../../results/abdullah_soundfont_comparison/README.md) cover two synthetic examples, one per transfer direction. Listener judgments of style, recognizability, and coherence remain to be collected.

Run the tests with the setup dependencies installed. The real-render tests require a SoundFont and the synthesis tools. They skip when those resources are unavailable.

```bash
python -m unittest discover -s tests -v
CSC575_TEST_SOUNDFONT=/usr/share/sounds/sf2/FluidR3_GM.sf2 \
  python -m unittest discover -s tests -p 'test_abdullah_rendering.py' -v
```
