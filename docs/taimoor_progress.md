# Taimoor: progress evidence and remaining work

Checkpoint: 12 November 2026. This file distinguishes Taimoor's contribution from
team components and preserves the limits of the evidence.

## Current implementation

The standalone arranger defines a beat-based MIDI/annotation contract; adapts
bass and chord templates to supplied harmony; and selects phrase plans using
dynamic programming, transition costs, and repeated-label consistency. The
experiment runner compares instrument substitution (B0), fixed patterns (B1),
adaptive selection (M), and a continuity ablation on matched inputs.

The original four synthetic fixtures remain engineering checks. The new
[source-derived checkpoint](../results/taimoor_evaluation/EVALUATION_SUMMARY.md)
uses 12 distinct compositions from Smit's dataset branch, with four development
and eight held-out-for-parameter-selection cases, balanced between the two
source genre folders. Each prepared excerpt is 16 bars, about 30-60 seconds.

## Status against the approved README indicators

| Indicator | Current status | Evidence and limits |
| --- | --- | --- |
| O1 PI1 basic: representation/interfaces with examples | Implemented | `model.py`, worked synthetic annotations, and 12 source-derived annotation JSONs. Team agreement and independent annotation review remain pending. |
| O1 PI2 basic: constrained bass/chord adaptation | Implemented and tested | Chord mapping, melody protection and bounds; 42 passing tests and 48/48 checkpoint raw-event audit passes. Harmony claims concern the supplied chord map. |
| O1 PI3 expected: descriptor retrieval and development-only parameters | Implemented; pilot selection completed | Transparent local costs and hard constraints; eight continuity settings evaluated using four development compositions only; style/continuity weights frozen at 1/4 before test evaluation. This is proxy-based selection in a small grid, not learned genre modeling. |
| O1 PI4 expected: phrase selection, transitions, repeated phrases, both styles | Implemented and demonstrated | DP objective verified against exhaustive search; repeated-label constraint tested; 32/48-second synthetic demonstrations and 30-60-second source-derived outputs in both directions. Real-source phrase grid is provisional. |
| O1 PI5 advanced: learned/pretrained matched comparison | Pending | No learned reranker or pretrained accompaniment comparison is claimed. |
| O2 PI1 basic: matched hypothesis, controls and outcomes | Implemented | B0/B1/M with shared input, target palette and B1/M pattern library. Explicit symbolic, technical and runtime outcomes. |
| O2 PI2 basic: experiment runner and logging | Implemented | Input IDs, source/annotation/code/output hashes, settings, traces, transformation times, planned denominators and failures. The implementation is deterministic. |
| O2 PI3 expected: held-out comparisons in both directions | Completed as an exploratory checkpoint | Eight composition-separated cases and 32 test conditions; invariant, accompaniment, failure and runtime analyses. Not the original 20-test-composition final study, and annotations are not independently reviewed. |
| O2 PI4 expected: selection/continuity ablations and interpretation | Symbolic pilot completed; listening interpretation pending | Fixed selection versus adaptive selection, and full versus zero continuity, with per-composition plans and texture/bass-jump comparisons. Anonymous playable materials and blank rating forms are prepared; no responses are claimed. |
| O2 PI5 advanced: sensitivity/validation trade-offs | Initial grid only | Development-only ratio sweep and frozen test comparison now exist. The broader final robustness analysis remains pending. |

The approved design README has not been rewritten to lower the original targets.
These statuses support progress-stage coding and experimental claims; they do
not certify full marks or complete the team's final evaluation commitments.

## Recorded results

- Original synthetic checkpoint: four fixtures, 16 conditions, 35 original tests,
  successful local reproduction and preliminary listening reported by Taimoor.
- Expanded suite: **42 passing tests**, including source-baseline applicability,
  crop/expression handling, development/test separation, decimal-tempo cases and
  deliberate melody corruption detection.
- Source-derived checkpoint: **48/48 conditions pass** both corrected technical
  checking and the independent raw-MIDI audit. All melody pitch/onset/offset/
  velocity events match the prepared source exactly in beat coordinates.
- Held-out subset: eight compositions / 32 conditions. Adaptive selection differs
  from fixed in four compositions. Continuity changes the plan in six of eight.
- Mean held-out phrase texture change: full **1.09** versus zero-continuity
  **3.17 notes/bar**. Mean boundary bass jump: full **1.96** versus zero-continuity
  **3.08 semitones**. These are descriptive proxies, not listener preferences.
- Target-reference descriptor distance: B0 **0.792**, B1 **1.073**, M **0.976**,
  zero-continuity **1.007**. The descriptor evidence does not establish that M
  outperforms B0 or that any output is perceptually superior.
- Matched listening materials: source and four conditions for each of the eight
  test compositions. Audio validation is recorded separately from music quality.

Per-composition results, parameter scores, source hashes, charts, and the
measurement correction are in `results/taimoor_evaluation/`.

## What the real-data pilot revealed

The first evaluation recorded 36/48 generator-check passes and 32/48 raw-audit
passes. Encoded MIDI tempo is an integer number of microseconds per beat; the
BPM approximation placed some downbeat notes just inside the preceding bar in
the evaluator and produced overly strict duration mismatches. Measurements now
use encoded timing and compare output duration with the actual prepared source.
Rechecking the same exports yields 48/48 passes, with all MIDI hashes unchanged.
The first run, first-run code, selected settings and repair record remain saved.
A fresh corrected-code repeat also passes 48/48 checks and selects the same 1/4
weights. It is a diagnostic repeat of an already inspected test set.

A related serialization regression exposed pretty_midi's truncation of floating
MIDI tempo. Future exports explicitly round constant-tempo encoding to avoid
one-microsecond drift across save/reload cycles. Tests cover three noninteger
BPM cases. No test-informed weight change was made.

Original source accompaniment can legitimately contain passing tones and notes
outside the generator's instrument ranges. B0 is now assessed for source event
preservation and valid timing; generator-only chord/register constraints apply
to B1/M/ablation. This distinction does not exempt B0 from melody checks.

## Boundaries and dependencies

- **Smit:** supplied MIDI collection and file inspection. Chord estimates and
  melody selections in this pilot were prepared in Taimoor's adapter; they are
  not claimed as Smit's completed annotations. Independent chord/phrase review,
  upstream acquisition/provenance documentation, and the final grouped corpus
  are still needed. The estimator conservatively flags 173/192 bars for review;
  a flag indicates ambiguity or within-bar variation, not proven error.
- **Vinay:** supplied the unchanged accompaniment feature extractor. Its four
  structural descriptors support the development-selection proxy. No trained
  classifier results or independent genre-quality validation are attributed to
  this checkpoint. Independent style and listening analysis remain his role.
- **Abdullah:** supplied the unchanged, pinned MIDI-to-WAV rendering implementation.
  It is reused for the matched audio materials, with consistent synthesis and
  loudness settings. This is integration evidence, not a new rendering
  contribution claimed by Taimoor.
- **Taimoor:** owns the input adapter, constraints, arrangement selection,
  development selection, controlled comparisons, audits, timing corrections,
  experiment records and method interpretation. The core demonstration remains
  runnable without trained models or an interface.

Per-bar chord estimates may simplify within-bar harmony. Four-bar grid boundaries
are not independently validated musical phrases. Source genre names are inherited
from Smit's folders. Artist-level split independence and alternate-version checks
are not established. These limitations must appear in the progress report.

## Additional waveform-based evaluation

An independent, pretrained CLAP audio-text model was run locally on the actual
rendered audio: four development-source controls, eight source excerpts, and
32 transformed output clips. A fixed 10-genre / three-prompt protocol and
full-coverage 10-second windows were used. No arranger setting was changed.

The forced Jazz/Rock choice agreed with only 2/4 development-folder labels; both
Rock-labelled development renderings favoured Jazz. A supplementary check on two
artist-labelled reference recordings, Kevin MacLeod's *Hot Swing* and *Rock on
Chicago* (CC BY 4.0), selected the expected genres for both. This difference
suggests that the project renderings and inherited labels need further review;
it does not establish a particular cause or model reliability.

On project outputs, CLAP's forced target-genre agreement was M 5/8 and B0/B1/
no-continuity 4/8 each. These are **diagnostic target-agreement counts, not
validated genre accuracy or human ratings**. Scores and segment/prompt details
are retained in `results/taimoor_audio_assessment/`. The model is not used to
assign final 1-5 style, recognizability, or coherence ratings. Global audio
embedding similarity is not a melody-recognizability measure.

A reference-guided listening form now supplies independently artist-labelled
Jazz and Rock audio anchors, plain-language recognizability/coherence scales,
an "I cannot judge" option, and CSV export. It distinguishes internal team
feedback from external listeners. All human fields remain unfilled until actual
responses are collected. The automated assessment attempt is a documented
limitation and lesson learned, not a completed perceptual study.

## Final-project goals and revised milestones

| Level | Concrete outcome | Evidence / milestone |
| --- | --- | --- |
| Basic | Deliver the CPU-capable arranger and a reproducible two-direction comparison even if integration is delayed. | Existing standalone code, synthetic negative controls, 12-composition pilot, hashes, logs and saved MIDI. Already demonstrable. |
| Expected | Review the real-source annotations, freeze the agreed final composition splits, and rerun matched B0/B1/M and ablations with documented failures and actual listening observations. | First obtain annotation/provenance handoff; then freeze final inputs/settings; then render and collect method-anonymized ratings; finally report per-composition and listener results. Retain the original 60-composition collection and 8-12 listener targets unless the team records an explicit scope revision. |
| Advanced O1 | Integrate one learned candidate reranker or compatible pretrained accompaniment model and compare it with the heuristic under identical preservation constraints. | Record compatibility, development-only model choices, output failures, runtime and independent evaluation. The ranker's own score cannot establish improvement. |
| Advanced O2 | Extend the pilot grid into a validation-selected sensitivity/robustness analysis across melody density, harmony complexity and both directions. | Predefine strata and settings before final held-out evaluation; report trade-offs, uncertainty and failure examples. The current eight-setting sweep is preliminary evidence only. |

For this progress submission, the remaining immediate human-dependent work is to
review the provisional annotations and record specific listening observations.
Do not invent ratings or describe developer listening as an external user study.
The report can then describe the completed engineering/pilot evidence and the
remaining final-project work accurately.
