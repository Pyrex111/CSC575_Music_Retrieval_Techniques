# Taimoor: source-derived evaluation checkpoint

Exploratory progress evidence, not a completed final-project study or a perceptual genre-quality result.

## What was evaluated

- 12 distinct compositions from Smit's pinned dataset branch: 4 development and 8 held-out for parameter selection, balanced by source folder genre.
- One 16-bar excerpt per composition, approximately 30-60 seconds, with an explicitly selected melody track.
- Four matched conditions: B0 instrument substitution, B1 fixed patterns, adaptive selection, and the continuity ablation.
- Melody/chord/phrase inputs are source-derived with provisional annotations. The four-bar grid is not independently reviewed phrase structure.
- No composition or exact source/prepared/melody-content hash crosses splits. Artist-level independence and alternate-version detection are not established.

## Development-only parameter selection

Only the four development compositions informed reference centers/scales and weight selection. Style weight was fixed at 1: globally scaling both weights cannot change the selected path.
The selection proxy combines distance to target-genre development-source descriptors and a separately measured boundary bass-jump penalty. It is not a listener rating or classifier accuracy.

| Continuity weight | Mean development selection proxy |
| ---: | ---: |
| 0 | 1.1599 |
| 0.1 | 1.1599 |
| 0.25 | 1.1599 |
| 0.5 | 1.1599 |
| 0.8 | 1.1599 |
| 1 | 1.1514 |
| 2 | 1.1431 |
| 4 | 1.1190 |

Selected style/continuity weights: **1 / 4**. Frozen selection and all original MIDI hashes are retained.
The selected continuity weight is at the upper grid boundary; it is a choice within this grid, not a demonstrated global optimum.

## Technical verification

All **48/48** conditions pass the corrected generator checks; all **48/48** pass the independent raw-event audit.
The audit finds zero melody pitch/onset/offset/velocity event differences. Tempo, metre, endpoints and supplied grid markers are retained. Generated B1/M/ablation accompaniment has no annotated chord-membership, register, or event-bound violations.
B0 retains original accompaniment. Original non-chord tones and source registers are measured, but they are not violations of the generator-only constraints.

### Diagnostic correction retained in the record

The first pass recorded 36/48 generator-check passes and 32/48 raw-audit passes. A BPM-float versus integer-MIDI-tempo discrepancy caused false bar-boundary harmony flags and false duration failures.
The corrected measurement reads encoded MIDI timing. Rechecking the identical saved files gives 48/48 passes in both checks; no arrangement or parameter was changed. Decimal-tempo regression cases were added. Future exports also round constant MIDI tempo rather than truncating it.
Because the measurement correction followed inspection of test diagnostics, these are diagnostic pilot results, not a pristine confirmatory hold-out experiment. The original evaluation, frozen selection, first-run code and repair record are preserved.

## Held-out comparisons

Each row below is averaged over eight test compositions. Lower descriptor distance indicates greater similarity to the small development reference profile, not proven genre quality. Lower texture change is not necessarily musically preferable.

| Method | Target-reference distance | Texture change (notes/bar) | Boundary bass jump (semitones) | Transform time (ms) |
| --- | ---: | ---: | ---: | ---: |
| instrument_only | 0.792 | 4.78 | 3.83 | 2.67 |
| fixed | 1.073 | 0.42 | 2.71 | 5.08 |
| adaptive | 0.976 | 1.09 | 1.96 | 5.54 |
| no_continuity | 1.007 | 3.17 | 3.08 | 5.38 |

Adaptive selection differs from the fixed arrangement in **4/8** held-out compositions. Matching B1 on the others is a valid result: context-aware selection does not guarantee a different plan.
Descriptor evidence does not justify claiming superiority to instrument substitution. No statistical significance, genre-recognition accuracy, or listener preference is claimed.

## Per-composition ablation interpretation

| Composition | Adaptive phrase plans | Events different from fixed | Texture: full / no-continuity | Bass jumps: full / no-continuity |
| --- | --- | ---: | ---: | ---: |
| La_Vie_en_rose | regular / regular / regular / regular | 0 | 0.50 / 0.50 | 0.00 / 0.00 |
| Let_There_Be_Love | busy / busy / busy / busy | 280 | 2.33 / 1.17 | 2.67 / 5.33 |
| Light_Years | release / regular / regular / regular | 50 | 1.50 / 8.17 | 1.33 / 2.33 |
| What_a_Wonderful_World.1 | build / regular / regular / regular | 43 | 1.75 / 0.83 | 2.67 / 4.00 |
| Brain_Stew | release / regular / release / release | 132 | 2.00 / 8.00 | 2.00 / 3.00 |
| Highway_To_Hell.1 | regular / regular / regular / regular | 0 | 0.00 / 0.00 | 4.00 / 4.00 |
| TNT | regular / regular / regular / regular | 0 | 0.50 / 4.67 | 2.33 / 2.33 |
| When_I_Come_Around | regular / regular / regular / regular | 0 | 0.17 / 2.00 | 0.67 / 3.67 |

- **La_Vie_en_rose:** continuity does not change the measured phrase-to-phrase texture change (0.50 versus 0.50 notes/bar). The target-reference distance is 1.189, compared with 1.189 for fixed patterns and 1.189 without continuity. These numbers describe an arrangement trade-off; auditory coherence has not been rated.
- **Let_There_Be_Love:** continuity increases the measured phrase-to-phrase texture change (2.33 versus 1.17 notes/bar). The target-reference distance is 0.537, compared with 1.192 for fixed patterns and 1.192 without continuity. These numbers describe an arrangement trade-off; auditory coherence has not been rated.
- **Light_Years:** continuity reduces the measured phrase-to-phrase texture change (1.50 versus 8.17 notes/bar). The target-reference distance is 1.080, compared with 1.184 for fixed patterns and 0.868 without continuity. These numbers describe an arrangement trade-off; auditory coherence has not been rated.
- **What_a_Wonderful_World.1:** continuity increases the measured phrase-to-phrase texture change (1.75 versus 0.83 notes/bar). The target-reference distance is 1.181, compared with 1.194 for fixed patterns and 1.194 without continuity. These numbers describe an arrangement trade-off; auditory coherence has not been rated.
- **Brain_Stew:** continuity reduces the measured phrase-to-phrase texture change (2.00 versus 8.00 notes/bar). The target-reference distance is 0.929, compared with 0.932 for fixed patterns and 0.879 without continuity. These numbers describe an arrangement trade-off; auditory coherence has not been rated.
- **Highway_To_Hell.1:** continuity does not change the measured phrase-to-phrase texture change (0.00 versus 0.00 notes/bar). The target-reference distance is 0.976, compared with 0.976 for fixed patterns and 0.976 without continuity. These numbers describe an arrangement trade-off; auditory coherence has not been rated.
- **TNT:** continuity reduces the measured phrase-to-phrase texture change (0.50 versus 4.67 notes/bar). The target-reference distance is 0.954, compared with 0.954 for fixed patterns and 0.805 without continuity. These numbers describe an arrangement trade-off; auditory coherence has not been rated.
- **When_I_Come_Around:** continuity reduces the measured phrase-to-phrase texture change (0.17 versus 2.00 notes/bar). The target-reference distance is 0.963, compared with 0.963 for fixed patterns and 0.953 without continuity. These numbers describe an arrangement trade-off; auditory coherence has not been rated.

## Annotation and interpretation limits

The conservative chord estimator flags **173/192 bars** for review because of low candidate separation, low coverage or disagreement between half bars. A flag is uncertainty, not proof of a wrong chord.
Per-bar chords approximate some within-bar changes. Annotated-harmony compliance establishes consistency with those supplied estimates; it does not prove that the original source harmony is fully preserved.
Source genre folders are Smit's labels, not newly validated genre ground truth. MIDI acquisition/provenance beyond the pinned team commit still requires Smit's documentation.
The original 60-composition dataset, independently reviewed musical annotations, and structured external listening remain outstanding. The four synthetic cases remain useful unit-test demonstrations and are not counted among these 12 source-derived compositions.

## Updated indicator assessment

| Indicator | Evidence now available | Scope / remaining limitation |
| --- | --- | --- |
| O1 PI1 basic | Representation, interfaces, source-derived annotation examples | Shared annotation review remains pending |
| O1 PI2 basic | Adaptation, preservation, independent checks, decimal-tempo correction | Preservation of supplied annotations rather than verified original harmony |
| O1 PI3 expected | Descriptor-distance selection, 8 development-only weight settings, frozen configuration | Small proxy-based selection; hand-authored pattern library |
| O1 PI4 expected | DP, transitions, exact repeated-pattern constraint, both target styles | Synthetic repeat tests; provisional real-source grid boundaries |
| O2 PI1 basic | Matched B0/B1/M conditions, controlled input/library/palette | Pilot protocol explicitly smaller than final study |
| O2 PI2 basic | IDs, settings, hashes, traces, times, retained failures and corrections | All evidence is reproducible from pinned sources |
| O2 PI3 expected | 8 composition-separated test cases in both directions; failures, invariants, changes, runtime | Exploratory diagnostic checkpoint; annotation and perceptual caveats |
| O2 PI4 expected | Fixed-selection and continuity ablations; per-composition symbolic interpretation | Specific listener observations remain to be recorded |
| Advanced | No learned reranker/pretrained comparison is claimed | Weight grid is a pilot, not a completed robust final sensitivity study |

## Attribution

- Smit: source MIDI collection and initial inspection, revision 3316077bdd47621f2eb9a506ee2900c0bb94dfe4.
- Vinay: unchanged accompaniment feature extractor, revision dcf7a4218243606e79055212830e08f4bfd9ff55; used here for a transparent descriptor proxy, not a trained classifier result.
- Taimoor workstream: input adapter/cropping, provisional annotations, constrained arrangement, development selection, controlled comparisons, audits, diagnostic fixes and interpretation.
- Abdullah: pinned rendering implementation used for the listening materials; no new audio or UI implementation is attributed to Taimoor.
