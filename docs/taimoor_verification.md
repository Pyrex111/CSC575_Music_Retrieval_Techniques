# Verification: what is established and what still needs evidence

## Independent technical audit

`workstreams/taimoor/independent_audit.py` reads exported MIDI through raw note-on/note-off events. It does not import the generator, annotation loader, candidate scorer, or original evaluator. It checks the named synthetic-fixture melody, exact beat positions and velocities, tempo, metre, phrase markers, excerpt length, unmatched note events, chord membership, register limits, and note bounds.

Run it on Taimoor's local outputs from the repository root:

```powershell
.\.venv\Scripts\python.exe -m workstreams.taimoor.independent_audit --results results/local/taimoor
```

It writes `independent_audit.json` and `independent_audit.md` in that results folder. This audit currently expects the generated fixtures and their `selected_melody` track name; adaptation to externally named real-song tracks is a later integration task.

The recorded repository outputs pass 16/16 checks. A separate corruption probe altered one melody pitch and its matching note-off event in a temporary copy. The audit rejected that output while accepting the three unchanged comparators. The original files were not changed.

The full adaptive method has a smaller average change in accompaniment-note density across adjacent phrases than its zero-continuity ablation: 17.33 versus 21.00 notes/bar for the Rock-to-Jazz fixtures, and 7.33 versus 11.00 for Jazz-to-Rock. This describes the implemented density-continuity effect. It does not establish smoother perceived transitions or better genre fit, and it is related to the selection objective rather than an independent quality measure.

## Perceptual verification protocol

The next experiment tests whether people hear the intended style while recognizing the source melody. A combination of repeatable technical measurements and listener evidence is consistent with the evaluation approach discussed by Yang and Lerch in the design bibliography [11].

Suggested initial pilot: two excerpts, one per transfer direction, and 3–5 listeners outside the development team. These are practical pilot numbers, not additional course requirements. The final study can follow the README's planned 8–12 participants and held-out examples.

1. Render source, instrument-only, fixed, and adaptive MIDI with the same renderer, SoundFont, sample rate, and documented loudness procedure. Use original generated MIDI rather than files re-exported after notation import. Keep the input and methods matched.
2. For each excerpt, play the source as a reference. Then play its three output versions under opaque IDs in a randomized, recorded order. Do not reveal the generating method or intended target genre before answers are collected.
3. Ask the same questions for each output: perceived style (Jazz, Rock, Other, or Unsure), source-melody recognizability (1–5), musical coherence (1–5), and any specific audible problem. Anchor recognizability from 1 = cannot recognize to 5 = clearly recognize; anchor coherence from 1 = very awkward/disconnected to 5 = coherent throughout.
4. Record listener ID, excerpt ID, opaque clip ID, playback order, answers, and optional musical experience. Keep the clip-to-method answer key separate from listener materials.
5. Decode the methods after collection. Report intended-style identification rates, recognizability/coherence distributions, and matched comparisons against both baselines. Retain listener/excerpt grouping in any uncertainty analysis. A small pilot supports descriptive findings only.

The primary hypothesis is that adaptive arrangement improves intended-style recognition relative to instrument substitution while retaining recognizability. Stronger performance than fixed patterns is an additional comparison to investigate. No quality threshold should be selected after seeing responses simply to make the method appear successful.

## Scope of conclusions

The current examples are authored synthetic fixtures. Even a positive listening pilot on them does not establish transformation quality on real songs. Repeat the protocol on reviewed real MIDI excerpts before making that broader claim.

Vinay's independently validated classifier can later provide supporting style evidence. The arranger's own hand-authored scoring profile should not serve as its genre verifier. Neither a low internal selection cost nor an AI opinion alone establishes musical quality.

Taimoor has reported that the local checks passed, supplied the resulting plot and summary, and auditioned the files, describing them as sounding fine. That is preliminary developer listening feedback, not a blinded external study.
