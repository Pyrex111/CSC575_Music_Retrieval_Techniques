# Rendering validation results

8/8 renders passed. 2 source references and 6 comparison WAVs passed.

| Case | Direction | Method | WAV length (s) | Synthesis (s) | Total (s) | LUFS | dBTP | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| development_jazz | jazz to rock | source | 32.50 | 0.620 | 2.913 | -23.00 | -13.43 | pass |
| development_jazz | jazz to rock | B0 | 32.50 | 0.513 | 2.644 | -23.00 | -12.28 | pass |
| development_jazz | jazz to rock | B1 | 32.50 | 0.514 | 2.699 | -23.00 | -13.24 | pass |
| development_jazz | jazz to rock | M | 32.50 | 0.621 | 2.818 | -23.00 | -13.10 | pass |
| development_rock | rock to jazz | source | 32.50 | 0.513 | 2.611 | -23.00 | -12.32 | pass |
| development_rock | rock to jazz | B0 | 32.50 | 0.413 | 2.624 | -23.00 | -12.82 | pass |
| development_rock | rock to jazz | B1 | 32.50 | 0.620 | 2.794 | -23.00 | -13.41 | pass |
| development_rock | rock to jazz | M | 32.50 | 0.616 | 2.784 | -23.00 | -12.15 | pass |

Synthesis time covers FluidSynth. Total time includes loudness processing and WAV checks.
