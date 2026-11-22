# SoundFont comparison for Objective 1 PI5

16/16 renders passed. 8/8 pairs passed the matching, audio-format, duration, and loudness checks.

The baseline bank and comparison bank use identical MIDI inputs, synthesis settings, duration alignment, and loudness targets. Bank details and hashes are in `comparison.json` and each bank's `results.json`.

| Case | Direction | Method | Baseline centroid (Hz) | Comparison centroid (Hz) | Change (Hz) | Spectrum distance | Loudness change (LU) | Controls |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| development_jazz | jazz to rock | source | 744.8 | 838.4 | +93.6 | 0.2575 | +0.00 | True |
| development_jazz | jazz to rock | B0 | 841.3 | 955.1 | +113.8 | 0.2637 | +0.00 | True |
| development_jazz | jazz to rock | B1 | 835.8 | 973.4 | +137.6 | 0.2755 | +0.00 | True |
| development_jazz | jazz to rock | M | 848.5 | 991.6 | +143.1 | 0.2736 | +0.00 | True |
| development_rock | rock to jazz | source | 789.0 | 841.5 | +52.5 | 0.2777 | -0.01 | True |
| development_rock | rock to jazz | B0 | 698.7 | 746.6 | +47.9 | 0.2697 | +0.00 | True |
| development_rock | rock to jazz | B1 | 683.5 | 763.2 | +79.7 | 0.2783 | +0.01 | True |
| development_rock | rock to jazz | M | 667.4 | 729.2 | +61.8 | 0.2628 | +0.00 | True |

## Measurement definitions

Spectra use non-overlapping 4096-sample Hann windows, with a zero-padded final window. Squared FFT magnitudes from both stereo channels are summed over the MIDI interval. The half-second release tail is excluded. The aggregate power spectrum is normalized to sum to one. The centroid is its frequency-weighted mean in Hz. Spectrum distance is half the sum of absolute differences between the two normalized spectra, from zero to one. Changes are comparison minus baseline. These descriptors measure changes in the rendered sound.

Synthesis and total processing times are recorded separately in each bank's render log. These are single-pass measurements including SoundFont loading.

## Evidence scope

Input evidence type: `synthetic_engineering_checks`. This comparison measures technical rendering consistency and acoustic sensitivity on the selected inputs. Genre preference, recognizability, and musical coherence require listener observations. No listener responses have been collected by this runner.
