# Rendering validation results

17/17 renders passed. 5 source references and 12 comparison WAVs passed.

| Case | Direction | Method | WAV length (s) | Synthesis (s) | Total (s) | LUFS | dBTP | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| development_jazz | jazz to rock | source | 32.50 | 0.715 | 4.252 | -23.00 | -12.13 | pass |
| development_jazz | jazz to rock | B0 | 32.50 | 0.622 | 3.648 | -23.00 | -12.52 | pass |
| development_jazz | jazz to rock | B1 | 32.50 | 0.215 | 3.189 | -23.00 | -12.81 | pass |
| development_jazz | jazz to rock | M | 32.50 | 0.222 | 3.333 | -23.00 | -12.64 | pass |
| development_rock | rock to jazz | source | 32.50 | 0.231 | 3.285 | -22.99 | -12.17 | pass |
| development_rock | rock to jazz | B0 | 32.50 | 0.215 | 3.389 | -23.00 | -11.45 | pass |
| development_rock | rock to jazz | B1 | 32.50 | 0.619 | 3.822 | -23.01 | -12.53 | pass |
| development_rock | rock to jazz | M | 32.50 | 0.617 | 3.611 | -23.00 | -12.25 | pass |
| verification_jazz | jazz to rock | source | 48.50 | 0.618 | 4.950 | -23.00 | -11.69 | pass |
| verification_jazz | jazz to rock | B0 | 48.50 | 0.617 | 4.944 | -23.00 | -12.56 | pass |
| verification_jazz | jazz to rock | B1 | 48.50 | 0.214 | 5.222 | -23.00 | -11.44 | pass |
| verification_jazz | jazz to rock | M | 48.50 | 0.457 | 5.572 | -22.99 | -11.29 | pass |
| verification_rock | rock to jazz | source | 48.50 | 0.216 | 5.169 | -23.01 | -12.28 | pass |
| verification_rock | rock to jazz | B0 | 48.50 | 0.316 | 4.544 | -23.00 | -12.39 | pass |
| verification_rock | rock to jazz | B1 | 48.50 | 0.616 | 5.467 | -23.00 | -12.63 | pass |
| verification_rock | rock to jazz | M | 48.50 | 0.622 | 4.875 | -23.00 | -12.35 | pass |
| abdullah_render_reference | Reference | source | 40.50 | 0.216 | 3.738 | -23.00 | -10.76 | pass |

Synthesis time covers FluidSynth. Total time includes loudness processing and WAV checks.
