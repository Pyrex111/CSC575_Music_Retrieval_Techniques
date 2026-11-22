# Rendering validation results

8/8 renders passed. 2 source references and 6 comparison WAVs passed.

| Case | Direction | Method | WAV length (s) | Synthesis (s) | Total (s) | LUFS | dBTP | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| development_jazz | jazz to rock | source | 32.50 | 0.514 | 2.959 | -23.00 | -12.13 | pass |
| development_jazz | jazz to rock | B0 | 32.50 | 0.513 | 2.695 | -23.00 | -12.52 | pass |
| development_jazz | jazz to rock | B1 | 32.50 | 0.212 | 2.458 | -23.00 | -12.81 | pass |
| development_jazz | jazz to rock | M | 32.50 | 0.213 | 2.400 | -23.00 | -12.64 | pass |
| development_rock | rock to jazz | source | 32.50 | 0.213 | 2.350 | -22.99 | -12.17 | pass |
| development_rock | rock to jazz | B0 | 32.50 | 0.214 | 2.272 | -23.00 | -11.45 | pass |
| development_rock | rock to jazz | B1 | 32.50 | 0.514 | 2.816 | -23.01 | -12.53 | pass |
| development_rock | rock to jazz | M | 32.50 | 0.513 | 2.859 | -23.00 | -12.25 | pass |

Synthesis time covers FluidSynth. Total time includes loudness processing and WAV checks.
