# Prepared-corpus integration checkpoint

Checkpoint: 20 November 2026. This extends Taimoor's November 12 pilot without
altering its saved results or progress PDF.

## Recorded evidence

- [Handoff audit](handoff_audit.json): all 60 source/annotation hashes, original
  loader outcomes, exact endpoint metadata changes, split conflicts and earlier
  pilot exposure. Compatible after normalization: **60/60**; original loader:
  **45/60**. No musical/control event or annotation content was changed.
- [Training-only results](smoke_results.json): **120/120** transformations and
  **120/120** independent raw-MIDI audits pass, with **zero** failures. Thirty
  training compositions use B0/B1/M and the continuity ablation. Fixed weights
  1/4 are inherited from the earlier pilot; no parameter selection occurred.
- [Candidate classifier manifest](style_dataset.csv): Vinay-compatible field
  names and excerpt melody indices. **Blocked for training/evaluation** by the
  train/validation composition conflict; do not bypass the loader's rejection.
- [Verification](verification.json): automated-test result, historical audit
  regression checks, code/input checksums, and the classifier-loader rejection.
- [Team report inventory and remaining work](../../docs/team_progress_inventory.md).

All 60 inputs remain computationally annotated and await review. Five of the
current 20 test compositions were in the earlier pilot, and two Ipanema variants
cross training/validation. These issues prevent treating these splits as a
clean confirmatory study. The saved preparation command intentionally returns
a nonzero exit status for the split conflict, after writing its diagnostic
record. The separate `smoke` command allows only training outputs, fits no
model, and retains the conflict in its report. No validation/test output,
classifier prediction, new audio assessment, or listener rating was generated.

## Reproduce

Use Python 3.10+ and `workstreams/taimoor/requirements.txt`. Start from this
checkpoint's code, and obtain the unchanged teammate data in a separate worktree:

```bash
git fetch origin Smit/dataset_preparation
git worktree add --detach ../csc575-smit-inputs ac9eb64673a4c6cfa086acbda5296f302dbf9ee9
python -m workstreams.taimoor.team_handoff prepare --source-root ../csc575-smit-inputs --output results/local/team_handoff
```

Inspect `handoff_audit.json`, especially `failures` and `cross_split_conflicts`.
The recorded dataset has no individual input failures but has one unresolved
split conflict. A training-only engineering check may proceed explicitly:

```bash
python -m workstreams.taimoor.team_handoff smoke --output results/local/team_handoff
python -m pytest tests/test_taimoor_arranger.py tests/test_taimoor_checkpoint.py tests/test_taimoor_team_handoff.py -q
```

The run directory contains normalized `prepared/` inputs and `outputs/` MIDI,
plus the three records committed here. Those generated MIDI files stay local
and can be reproduced from the pinned branch; paths in JSON/CSV are relative
to that run directory. Use a new empty output directory for each preparation;
existing evidence is never silently overwritten. A changed MIDI, annotation,
or classifier manifest stops the smoke run before arrangement.

The adapter belongs to Taimoor. Smit owns the supplied data and automatic
annotations; Vinay owns the classifier interface and evaluation code. The raw
audit now handles explicitly indexed, unnamed melodies without importing the
arranger or evaluator. It rejects raw tracks with ambiguous channel/program
mapping rather than guessing an instrument index.
