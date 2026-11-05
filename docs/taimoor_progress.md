# Taimoor: progress evidence and next steps

## Scope of this checkpoint

The current main branch was inspected at commit `2295649a2e3d6f47a9adebfceae9c243a9fda517`. It contained the approved design README and no implementation files. This checkpoint supplies an independently runnable arrangement prototype, engineering comparisons, and reproducible evidence. It does not infer that teammates have done no work outside the repository.

The instructor awarded the design specification 10/10, approved the basic and expected indicators, and requested more independent contributions, stronger advanced objectives, and consideration of audio work. This implementation addresses independence by accepting reviewed example inputs directly, without requiring the team's unfinished dataset, classifier, or UI.

## Status against Taimoor's existing objectives

| Objective / indicator | Status | Evidence and remaining work |
| --- | --- | --- |
| O1 PI1 basic: representation/interfaces | Implemented for the supported scope | `model.py`, annotation examples, and the workstream README define beat coordinates, melody selection, chord maps, phrase markers, and pattern interfaces. Team agreement is still needed. |
| O1 PI2 basic: constrained adaptation | Implemented and engineering-tested | Templates map onto supplied chords; selected melody is protected. Export/reload and all-root chord/register tests are included. Real-song review remains. |
| O1 PI3 expected: style-aware retrieval | Prototype only | Candidates are scored against hand-authored density/offbeat profiles. No real-data validation, GMD library, or parameter selection has been completed. |
| O1 PI4 expected: phrase-level selection | Prototype demonstrated | Dynamic programming, continuity penalties, repeated-phrase assignments, and 32/48-second outputs in both directions work on synthetic fixtures. Real excerpts and independent musical assessment remain. |
| O1 PI5 advanced: learned/pretrained comparison | Not implemented | A concrete proposed refinement is below. No model compatibility or training result is claimed. |
| O2 PI1 basic: matched experiment design | Implemented for engineering demonstration | Controlled B0/B1/M reference conditions and a continuity ablation use matched inputs, harmony, and palettes. The real-music experimental protocol remains to be frozen. |
| O2 PI2 basic: experiment runner | Implemented | Saves IDs, inputs/output hashes, source-code hashes, configuration, traces, versions, and transformation time. No randomness is used. |
| O2 PI3 expected: held-out comparisons | Not completed | Only generated fixtures have been evaluated. No real-composition held-out results exist. |
| O2 PI4 expected: ablations | Engineering pilot only | Fixed choice versus adaptive choice, and full selection versus zero continuity, have been executed. Interpretation on real music and listener evidence remain. |
| O2 PI5 advanced: robustness/sensitivity | Not completed | Default weights are documented, not optimized; no completed validation-selected sensitivity study is claimed. |

## Recorded engineering results

See `results/taimoor_progress/summary.md` and `results.json` for the saved run. Four original synthetic 16-bar fixtures produce 16 conditions across Rock-to-Jazz and Jazz-to-Rock directions. Development examples last 32 seconds and verification examples last 48 seconds.

- All 16 exported MIDI files were reopened and passed the selected-melody, excerpt-duration, tempo, metre, and phrase-marker checks.
- No generated accompaniment chord-membership, register, or event-bound violations were found in the recorded fixtures.
- Adaptive accompaniment differed from the fixed comparator in every fixture. This confirms different event arrangements, not better target-genre quality.
- The continuity ablation changed the final phrase's selected plan in the recorded examples. This confirms that the continuity term affects selection; listener preference remains unknown.
- The automated suite contains 35 passing cases, including a brute-force comparison of the optimization objective, deliberately corrupted melody detection, selection of a melody outside the first track, unsupported-input rejection, repeated-phrase consistency, and reproducibility checks.

Recorded repository tests and outputs were generated in the environment listed in `results.json`. Taimoor subsequently reported successful local execution, supplied his plot and summary (all 16 rows passed the reported constraints), and auditioned the outputs, describing them as sounding fine. This is preliminary developer feedback. No blinded listener results or WAV render-quality audit are claimed.

A [separate raw-MIDI audit and listening protocol](taimoor_verification.md) now supplement the original checks. The saved repository outputs pass 16/16 independent event-level audits, and a temporary deliberately corrupted melody was correctly rejected. Reports are saved as `results/taimoor_progress/independent_audit.json` and `independent_audit.md`.

## Addressing the independence feedback

The standalone demonstration needs only this repository and Python dependencies. It creates original engineering fixtures, then loads the same annotation format intended for team-reviewed excerpts. Minimal B0/B1 comparators are present solely to exercise Taimoor's experiment runner. Smit retains ownership of the project's corpus and baseline contribution, Vinay retains independent style/perceptual evaluation, and Abdullah retains audio rendering and interface work.

Each output records the selected plans and costs. Taimoor can explain and demonstrate one input's melody/chord contract, chord adaptation, an adaptive output, its fixed-pattern comparison, and its continuity ablation without waiting for another component.

## Proposed advanced-indicator refinements for review

The approved root README has not been silently rewritten. These are proposals to discuss with the instructor and Vinay before treating them as revised commitments.

**Objective 1, advanced:** Develop a learned candidate-ranking extension using labelled development comparisons, with composition-grouped training/validation separation. Compare it with the transparent heuristic ranker using the same candidate library, preservation constraints, and phrase selector. Freeze the choice before a held-out comparison; report ranking agreement, constraint failures, runtime, and a separate method-anonymized listening comparison. The ranking model's own score must not serve as independent proof of quality. Taimoor would own integration and comparative experiments; model ownership and any shared labels must be explicitly agreed with Vinay to avoid duplicated claims.

**Objective 2, advanced:** Extend the weight study into a validation-selected robustness analysis across melody density, harmonic complexity, and both transfer directions. Predefine the parameter grid and comparison protocol, select the configuration on development inputs, and evaluate once on held-out compositions. Report per-composition effects, uncertainty, failure cases, and whether the selected configuration remains useful across those strata. Small samples must be labelled exploratory. This is more assessable than an unspecified sensitivity sweep, but the data and evaluation effort still require planning.

These extensions remain pending and have not been counted among completed work.

## Audio feedback

The prototype exports actual MIDI and is ready for Abdullah's synthesis component. Rendering MIDI as audio will provide listening outputs, but the instructor also suggested exploring audio generation. A bounded text-prompted audio experiment can be proposed separately with a recorded model/version, prompts, outputs, and evaluation question. Genre-matching generated audio must not be described as source-song transformation unless melodic/structural retention has actually been tested. No model, paid service, or new audio-generation commitment is selected here.

## Immediate next actions

1. Local execution and preliminary listening have been reported. Next, record specific recognizability, style, and transition observations and carry out the blinded pilot in the verification protocol.
2. Agree the provisional annotation/pattern interface with Smit and obtain at least two reviewed real MIDI excerpts, ideally one per transfer direction, with provenance and permitted use.
3. Apply the existing runner to those development examples and inspect failures before freezing the larger evaluation protocol. Such a small check is a pilot, not the planned held-out study.
4. Agree the descriptor/ranking handoff with Vinay and provide exported conditions to Abdullah for consistent audio rendering.
5. Use the progress-report instructions and exact deadline, once supplied, to integrate evidence and finalize revised advanced indicators.

## Progress-report text to adapt after review

The arrangement workstream now has a standalone symbolic prototype that accepts a MIDI excerpt with an explicitly selected melody, reviewed per-bar chords, and supplied phrase boundaries. It adapts authored accompaniment patterns to those chords and uses dynamic programming to select phrase plans while accounting for continuity and repeated phrases. An experiment runner compares instrument substitution, fixed patterns, adaptive selection, and a continuity ablation, with saved configurations and event-level preservation checks.

Initial engineering verification used four original synthetic excerpts lasting 32 or 48 seconds. All 16 exported conditions preserved the selected melody, tempo, duration, metre, and phrase markers under the implemented checks. The accompanying 35-case test suite includes an independent brute-force check of the selection objective. These results demonstrate execution and constraint preservation; they do not establish genre-transfer quality. The next stage is to integrate reviewed real MIDI examples, validate the hand-authored profiles, and obtain independent musical and perceptual evidence. Learned ranking and the advanced robustness study remain pending.
