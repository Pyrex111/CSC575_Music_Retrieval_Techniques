# Objective 1 PI5 SoundFont comparison

PI5 compares a second SoundFont on a small matched subset. This run uses the original `development_jazz` and `development_rock` engineering fixtures, with source/B0/B1/M rendered under TimGM6mb and FluidR3. This gives eight identical MIDI inputs and 16 WAVs. The arranger snapshot is `387769d6ebdc44770535b0b6b42cf6d4e2bf85a3`. Input hashes and the `synthetic_engineering_checks` evidence label are recorded in each bank's `results.json`.

| Bank | Package | SoundFont terms | Renders passed | LUFS range | Highest true peak (dBTP) | Median synthesis (s) |
| --- | --- | --- | --- | --- | ---: | ---: |
| TimGM6mb | `timgm6mb-soundfont 1.3-5` | GPL-2.0-only | 8/8 | -23.01 to -22.99 | -11.45 | 0.363 |
| FluidR3 GM | `fluid-soundfont-gm 3.1-5.3` | MIT | 8/8 | -23.00 to -23.00 | -12.15 | 0.565 |

Each WAV contains 1,433,250 stereo PCM16 frames at 44,100 Hz, giving 32.5 seconds for a 32-second MIDI interval and a 0.5-second release tail. All eight pairs passed the matching and loudness controls. No output was clipped or peak limited. Synthesis times include loading the bank. The logs describe one pass on the recorded host. [TimGM6mb results](baseline/results.json) · [FluidR3 results](comparison/results.json)

Changing the SoundFont changed the power-weighted spectral centroid by +47.9 to +143.1 Hz across the eight pairs. The normalized power-spectrum distance ranged from 0.2575 to 0.2783 on its 0-1 scale. Paired loudness differed by at most 0.01 LU. [Per-pair measurements and definitions](summary.md) · [Unrounded measurements](comparison.json)

| Case | TimGM6mb B0 centroid (Hz) | TimGM6mb B1 centroid (Hz) | FluidR3 B0 centroid (Hz) | FluidR3 B1 centroid (Hz) |
| --- | ---: | ---: | ---: | ---: |
| Jazz to Rock | 841.3 | 835.8 | 955.1 | 973.4 |
| Rock to Jazz | 698.7 | 683.5 | 746.6 | 763.2 |

B0 has the higher power-weighted centroid under TimGM6mb, while B1 has the higher value under FluidR3 in both cases. This demonstrates sensitivity of an audio descriptor ordering to the chosen sounds. The technical conclusions about valid, matched-duration, loudness-controlled rendering hold for this subset under both banks. Future musical comparisons need a common bank and listener evidence for style fit, recognizability, and coherence. The run contains no human ratings.

Reproduce the run with the [comparison command](../../workstreams/abdullah/README.md#compare-a-second-soundfont-for-pi5). The generated WAVs belong under `results/local/abdullah_soundfonts/`. The committed manifests resolve their audio paths relative to each bank's generated folder. The saved logs, hashes, metrics, and notices describe the measured run. [SoundFont provenance](soundfont_provenance.json)

An additional isolated bass-note probe at 22,050 Hz exposed a residual loudness mismatch with FluidR3. The original single-pass gain reached -23.45 LUFS. The renderer now remeasures and corrects constant gain for up to three passes within the peak ceiling. That probe reached -22.97 LUFS in two passes. All 16 full-length comparison WAVs reached the target tolerance in one pass. The probe measurements are retained [before the correction](normalization_probe_before.json) and [after the correction](normalization_probe_after.json).

The eight-test suite passed with each SoundFont and no skipped tests. The added coverage checks subset selection, known-tone spectral measurements, silent audio, pair controls and hashes, rejection of identical SoundFont contents, and preservation of an existing output when loudness correction fails to converge. Independent FFprobe, SHA-256, loudness, clipping, and vectorized spectral checks are saved in [verification.json](verification.json). The listening loader accepted six comparison rows per bank, with all referenced WAVs present. [TimGM6mb test run](tests_timgm6mb.log) · [FluidR3 test run](tests_fluidr3.log)
