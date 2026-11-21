# Taimoor: advanced implementation and team handoff

Checkpoint: 21 November 2026. This is a development implementation and experiment
record. It does not replace the submitted November 12 progress report or claim
that final annotation review, final held-out evaluation, or listening is complete.

## What is now implemented

| Deliverable | Implementation and evidence |
| --- | --- |
| Learned candidate reranker | `learned_ranking.py` connects Vinay's unchanged feature extraction, model constructors, and probability scoring to Taimoor's candidate selector. |
| Constrained learned selection | An optional scorer adds `beta * phrase_bars * (1 - target_probability)` to each existing heuristic cost. The candidate library, chord adaptation, repeated-label constraints, and continuity DP are retained. B0/B1 cannot receive the scorer. |
| Development model workflow | Original training inputs are divided by composition into 20 fitting and 10 internal development-check cases. Logistic regression and random forest are compared using three-fold grouped CV on the 20 fitting cases. Scaling is fitted inside each logistic-regression fold. |
| Sensitivity runner | Nine continuity settings crossed with three learned-penalty weights: 27 configurations / 270 development conditions. Melody-density and harmonic-complexity strata use median thresholds from fitting inputs only; both directions are reported. |
| Matched comparison | Ten internal development cases, six conditions: B0, B1, heuristic M, no continuity, learned M with matched continuity, and the development-selected configuration. All 60 outputs pass technical checks and independent raw-MIDI audits. |
| Uncertainty summaries | Paired composition bootstrap intervals for learned-versus-heuristic and selected-versus-heuristic structural metrics. These are exploratory development intervals, not final significance tests. |
| Data handoff proposal | A proposed composition-grouped manifest removes the Ipanema alternate version and excludes all earlier-pilot and original-training groups from test. It is a proposal, not an applied or agreed split. |
| Review and rendering handoffs | Blank hash-bound annotation review CSV, readiness checks, and 70 pending MIDI-to-audio rows: ten sources plus sixty comparison outputs. No new audio or human ratings are claimed. |

The [evidence bundle](../results/taimoor_advanced/README.md) contains the recorded
scores, selection, comparisons, split proposal and verification. The local model
binary and generated MIDI are reproducible run artifacts, not committed assets.

## Observed development results

- All **76 automated tests** pass. New checks cover a repeated-phrase optimization
  oracle, zero-weight/default equivalence, invalid scores, protection of B0/B1,
  development/test separation, artifact drift, paired denominators, and portable
  manifest paths.
- All **270/270 grid conditions** and **60/60 comparison conditions** pass
  technical and independent raw-event checks.
- Grouped fitting-pool CV mean macro-F1: logistic regression **0.649**, random
  forest **0.414**. Logistic regression was selected before the ten-case
  development check. On those ten source clips it predicts 9/10 folder labels
  correctly, macro-F1 **0.899**. These small, provisional-label diagnostics are
  not final held-out classification accuracy or genre-transfer results.
- At the matched continuity setting 4, the learned term changes **4/10**
  arrangements relative to heuristic M. Mean target-reference descriptor
  distance is **1.420** for learned M versus **1.431** for heuristic M. These
  descriptors are internal structural proxies, not independent proof of quality.
- The grid selects **continuity 0.5 / learned weight 1**, with style weight fixed
  at 1. The selected configuration changes **5/10** arrangements relative to
  heuristic M. It is a provisional development choice, not the final frozen
  project configuration.
- B0 has a lower mean descriptor distance (**0.943**) than either adaptive
  variant on this development sample. Superiority over instrument substitution
  is therefore not established. Lower measured texture/bass change is also not
  automatically better music.

## Concrete coordination requests

### Smit: corpus and annotation decisions

1. Review the [proposed manifest](../results/taimoor_advanced/proposed_manifest.csv)
   and [split rationale](../results/taimoor_advanced/split_proposal.json). Keep
   `jazz_015` as the retained Ipanema version and exclude `jazz_020`, or document
   an alternative composition-grouped decision.
2. The proposal has **30 train / 9 validation / 20 test** distinct compositions.
   Supply one reviewed **Jazz validation** replacement to recover 60 distinct
   compositions and the original 30/10/20 target. Existing inspection metadata
   suggests `A_Taste_of_Honey.mid`, `Christmas_Song.mid`, or
   `It_Dont_Mean_a_Thing.mid`; none has been automatically selected or annotated.
3. Five earlier-pilot test compositions move to proposed validation; five
   previously unscored validation compositions replace them in proposed test.
   The ten moves and retained case IDs are listed in the proposal.
4. Confirm melody choices, per-bar chords, phrase labels, genre labels and source
   provenance. Fill actual review outcomes in the [review CSV](../results/taimoor_advanced/annotation_review.csv).
   Its status fields start blank. Record artist/alternate-version limitations;
   artist independence is not assumed from filename grouping.

### Vinay: model and evaluation review

1. Review the 20/10 internal development partition and [CV record](../results/taimoor_advanced/classifier_cv.json).
   It uses only the original training pool. The original validation and test
   inputs are excluded from model fitting, scoring, parameter selection and
   arrangement generation in this implementation.
2. Confirm the adapter's fixed-duration convention. Vinay's original 21-feature
   extractor is unchanged, but a text endpoint anchors duration on a temporary
   MIDI copy. Candidate feature views are phrase-local; fitting views are full
   excerpts. Assess that domain difference, instrument-dependent bass detection,
   tempo dependence, and model reliability before final use.
3. The wrapper reuses `create_models` and `calculate_style_score`. It deliberately
   does not call the complete `train_and_select_model` CLI here, because that
   function also predicts the project's test set. No trained model is being
   attributed to Vinay as a previously delivered artifact; Taimoor's runner
   fitted this prototype using his unchanged constructors.
4. Arrange independent final evaluation. The classifier score used for candidate
   selection cannot also serve as independent proof of genre improvement.

### Abdullah: rendering and eventual playback

1. Use the [70-row rendering handoff](../results/taimoor_advanced/render_handoff.csv)
   with the existing `render_midi` implementation at revision
   `98510f50b262683e227a09b4017788e85800e93a`.
2. Render each source and its six comparisons with one SoundFont, 44.1-kHz PCM16,
   the same duration policy, and the documented -23 LUFS / peak-ceiling process.
   Preserve the additional `learned` and `development_selected` condition labels;
   the old three-method batch manifest needs that label extension.
3. Generated audio remains pending. These are development materials. Use the
   approved final examples for the external listening study; distinguish any
   internal development feedback from final listener responses.

## What remains open

- Team agreement, a replacement composition, and genuine input reviews. The
  readiness command currently returns **false** rather than treating the
  proposal or blank review form as approval.
- Final classifier validation and controls, final configuration selection on
  the agreed development split, and one frozen final-test comparison.
- Actual listening responses and their interpretation. The original 8-12
  listener target remains; no ratings have been manufactured.
- Final integration/reporting and explicit attribution of each teammate's work.

For indicator reporting, O1 PI5 now has an implemented learned extension and a
matched **development** comparison. O2 PI5 now has a broader development
sensitivity/strata analysis. Both still need the agreed final-study evidence
before being presented as fully validated advanced achievements.
