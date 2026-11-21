# Learned reranker and expanded development study

Checkpoint: 21 November 2026. **Development implementation and diagnostics only.**
Final reviewed data, final held-out evaluation and human listening remain pending.
The [coordination handoff](../../docs/taimoor_advanced_handoff.md) lists concrete
requests for Smit, Vinay and Abdullah.

## Evidence

| Record | What it establishes |
| --- | --- |
| [Model manifest](model_manifest.json), [development roles](development_roles.json), [CV](classifier_cv.json) | Vinay's pinned constructors and 21 features; original training pool only; 20 fitting compositions, three-fold grouped model comparison, ten separate internal development-check compositions. |
| [Development source-label check](development_classifier_check.json) | Logistic regression predicts 9/10 internal source-folder labels, macro-F1 0.899. Fitting-pool CV macro-F1 is 0.649 versus 0.414 for random forest. Labels and the small development sample require caution. |
| [Protocol](protocol.json), [27-setting grid](grid_summary.csv), [strata](strata_summary.csv) | Continuity weights 0 through 8 crossed with learned weights 0, 0.25, 1; 270/270 technical and raw-event passes. Strata thresholds use fitting inputs only. |
| [Development selection](development_selection.json), [grid figure](sensitivity_grid.png) | Selected continuity 0.5 / learned weight 1, with style weight fixed at 1. This is an internal development choice, not the project's final configuration. |
| [Matched results](comparison_results.json), [summary](comparison_summary.csv) | Ten internal development inputs and six conditions, 60/60 technical and independent raw-MIDI audit passes. Learned M at the matched continuity 4 changes 4/10 arrangements relative to heuristic M. |
| [Paired intervals](paired_development_intervals.json) | Composition-paired exploratory bootstrap diagnostics. The learned-versus-heuristic descriptor-distance difference is -0.0116 with a 95% bootstrap interval of approximately [-0.0546, 0.0166], spanning zero. |
| [Split proposal](split_proposal.json), [candidate manifest](proposed_manifest.csv) | A proposed 30/9/20 split of 59 distinct compositions, excluding the duplicate version and previously observed development groups from test. One Jazz validation replacement remains necessary. No split change was applied to teammate data. |
| [Review form](annotation_review.csv), [readiness](readiness.json) | Blank, hash-bound review requests. Final readiness is false; team agreement and actual input reviews are not inferred. |
| [Renderer handoff](render_handoff.csv) | Seventy hash-verified MIDI references for ten sources and sixty comparisons. Audio is not yet rendered; no listener responses are supplied. |
| [Verification](verification.json), [diagnostic corrections](diagnostic_corrections.json) | 76 passing tests; 16 original default outputs remain byte-identical; historical 16/16 and 48/48 raw audits pass. A first-run descriptor boundary error and subsequent corrections are retained. |

The learned probability is a generation score, not independent evidence of
musical quality. B0's mean development descriptor distance is 0.943, lower than
heuristic M (1.431), learned M at matched continuity (1.420), and the selected
configuration (1.361). No superiority over instrument substitution is claimed.
These references are fitted on the new 20-case fitting cohort with explicit
duration anchoring; distances are not directly comparable with the November 12
pilot's different references. Timings include score-cache reuse and are not a
controlled runtime benchmark.

## Reproduce

Install the optional dependencies and fetch unchanged teammate worktrees:

```bash
python -m pip install -r workstreams/taimoor/advanced_requirements.txt
git fetch origin Smit/dataset_preparation vinay/style-evaluation
git worktree add --detach ../csc575-smit-inputs ac9eb64673a4c6cfa086acbda5296f302dbf9ee9
git worktree add --detach ../csc575-vinay-inputs dcf7a4218243606e79055212830e08f4bfd9ff55
python -m workstreams.taimoor.team_handoff prepare --source-root ../csc575-smit-inputs --output results/local/team_handoff
```

The current corpus writes a complete input audit but deliberately returns a
nonzero status for its composition-group conflict. Inspect that record. The
following explicit development workflow uses only original training records;
it does not bypass that conflict for a final evaluation:

```bash
python -m workstreams.taimoor.advanced_study fit-development --handoff results/local/team_handoff --output results/local/advanced --vinay-root ../csc575-vinay-inputs
python -m workstreams.taimoor.advanced_study sensitivity --handoff results/local/team_handoff --output results/local/advanced --vinay-root ../csc575-vinay-inputs
python -m workstreams.taimoor.advanced_study compare-development --handoff results/local/team_handoff --output results/local/advanced --vinay-root ../csc575-vinay-inputs
python -m workstreams.taimoor.split_proposal propose --handoff results/local/team_handoff --output results/local/proposed_splits --source-root ../csc575-smit-inputs
python -m workstreams.taimoor.split_proposal readiness --output results/local/proposed_splits
python -m scripts.summarize_taimoor_advanced --advanced results/local/advanced --handoff results/local/team_handoff --proposal results/local/proposed_splits --output results/local/advanced_evidence
python -m pytest tests/test_taimoor_arranger.py tests/test_taimoor_checkpoint.py tests/test_taimoor_team_handoff.py tests/test_taimoor_advanced.py tests/test_taimoor_advanced_summary.py -q
```

Each output directory must be new for preparation/fitting/export. Frozen code,
model, feature order, input hashes, references and protocol are verified between
stages. Changed artifacts require a new run. The runner refuses to freeze a
selection if any planned grid configuration fails. The local model and generated
MIDI stay under `results/local/`; they are recreated by these commands.

Paths in the exported proposed and rendering CSVs resolve relative to those CSV
files. The committed CSVs reference the recorded local run directories
`team_handoff_20261120` and `taimoor_advanced_20261121_v3`; they become playable
handoffs when those local artifacts are present. A fresh export rebases paths to
its own run directories. The candidate manifest passes Vinay's existing schema
and composition-group loader but is not a complete or approved final dataset.

Taimoor owns the selector adapter, constrained integration, experiment workflow,
split proposal and comparisons. Vinay owns the reused feature/model/scoring
functions, Smit the supplied excerpts/annotations, and Abdullah the renderer
intended for the pending audio handoff. Their source files remain unchanged.
