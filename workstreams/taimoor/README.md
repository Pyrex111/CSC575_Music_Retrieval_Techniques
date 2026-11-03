# Taimoor: constrained arrangement prototype

This independently runnable workstream implements the arrangement and experiment-runner parts of Taimoor's design objectives. It is a progress-stage prototype, using hand-authored templates and original synthetic MIDI fixtures. It does not require Smit's dataset, Vinay's classifier, or Abdullah's renderer.

## Run it

From the repository root, with Python 3.10 or later:

```bash
python -m venv .venv
```

Activate the environment with `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on Linux/macOS. Then run:

```bash
python -m pip install -r workstreams/taimoor/requirements.txt
python -m pytest tests/test_taimoor_arranger.py -q
python -m workstreams.taimoor.run --output results/local/taimoor --plots
```

The demonstration creates four source MIDI fixtures and their reviewed-by-construction chord/phrase annotations, then runs four comparison conditions per input. Two excerpts last 32 seconds and two last 48 seconds. Generated files include source/transformed MIDI, one comparison figure per input, `results.json`, and `summary.md`. `results/taimoor_progress` contains the recorded development-environment run for the progress report; use a different output directory for new runs.

Open the MIDI in a MIDI-capable player or DAW to audition it. This component does not produce WAV, install a SoundFont, or implement the team's listening interface. Those remain integration tasks with Abdullah. No new text-to-audio model is included.

## What is implemented

1. **Input contract:** constant-tempo 4/4 MIDI plus an explicit melody-track index, reviewed chord per bar, excerpt length, and supplied phrase boundaries.
2. **Chord adaptation:** bass template indices map to supplied chord tones. Chord voicings stay within defined registers. The chord progression is not inferred or changed.
3. **Context-aware candidates:** three team-authored patterns per target preset, arranged into five phrase plans: sparse, regular, busy, build, release.
4. **Selection:** exact dynamic programming over phrase candidates, with continuity cost and a repeated-label constraint. Repeated A phrases reuse the same pattern plan relative to their phrase boundary, adapted to each occurrence's chord map.
5. **Protection:** melody notes and associated expressive MIDI controls are copied from the selected source instrument. Exported MIDI is reopened to check pitch, timing, tempo, duration, phrase markers, bounds, and accompaniment chord membership.
6. **Evidence:** per-input/per-method output hashes, configuration, selection traces, Python/package versions, source-code hashes, and transformation times.

The initial pitch ranges are bass MIDI 36–60 and chords MIDI 48–84. MIDI programs are zero-based. Only the accompaniment instruments are changed; the melody instrument is retained.

## Selection method

Each phrase has five candidate plans built from the same target-style pattern library. Local cost penalizes disagreement with a transparent accompaniment-density profile based on melody activity, plus a preset-specific offbeat profile. Sparse melody sections favour more active accompaniment, while dense sections favour less activity. These profiles and weights are engineering defaults, not fitted parameters or learned genre descriptions.

The sequence objective is:

```text
style_weight * sum(local_cost for each phrase)
  + continuity_weight * sum(transition_cost between adjacent phrases)
```

Transition cost combines the bass pitch jump across the phrase boundary and the change in accompaniment event density. The search state retains the previous candidate and live assignments for repeated phrase labels. A repeated label must select the same plan. Once that label's final occurrence is processed, its assignment can be discarded. A configurable state limit raises an explicit error instead of silently changing to an approximate search.

A unit test independently enumerates all valid candidate combinations for an A/B/A/C example and verifies that the dynamic-programming solution attains the minimum defined cost. Another test verifies that a sufficiently large continuity weight changes the chosen sequence and reduces the transition term. This establishes correctness for the defined objective, not musical superiority.

## Comparison conditions

| Runner method | Meaning | Relationship to the project plan |
| --- | --- | --- |
| `instrument_only` | Retain source accompaniment events and change pitched accompaniment programs. | Minimal B0 reference comparator. |
| `fixed` | Use the regular target-style template throughout. | Minimal B1 comparator using this workstream's candidate library. |
| `adaptive` | Select phrase plans with context and continuity, preserving repeated-label assignments. | First prototype of M. |
| `no_continuity` | Run the same selection with continuity weight zero. | Taimoor's continuity ablation. |

The comparators make this demonstration self-contained. They are not evidence that Smit has implemented his assigned baseline/data work. `fixed` also represents removal of adaptive choice. B1 and M share palettes, chord maps, melody, duration, and pattern library. All methods preserve the selected melody; preservation alone cannot distinguish genre quality.

## Use a team-provided MIDI excerpt

Create an annotation JSON alongside a cropped constant-tempo 4/4 MIDI file. A complete example is generated in `results/local/taimoor/fixtures/development_rock.json`. Important fields are:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1`. |
| `case_id` | Stable filename-safe identifier: starts with a letter/digit, followed by letters, digits, underscores, dots, or hyphens. Directory separators are rejected. |
| `source_style` | `rock` or `jazz`; the runner selects the opposite target. |
| `split` | Provenance label, e.g. `development` or `test`; merely setting this field does not establish a valid experimental split. |
| `midi_path` | File path relative to the annotation JSON. |
| `melody_track` | Zero-based index in `pretty_midi.PrettyMIDI(...).instruments`, not a raw MIDI track number or MIDI channel. |
| `tempo_bpm` | Must match the MIDI's constant tempo. |
| `time_signature` | `[4, 4]`. |
| `bars` | Total complete bars. MIDI end-of-track time must match. |
| `chords` | One object per bar: `root_pc` 0–11, distinct `intervals` including 0, e.g. C major `{ "root_pc": 0, "intervals": [0, 4, 7] }`. |
| `phrases` | Contiguous objects with `label`, `start_bar` (zero-based), and `bars`. A repeated label must have the same length. |

Supported chord intervals are supplied pitch classes, not a chord-symbol parser. Major/minor triads and seventh-chord interval sets are tested. Chord changes within a bar, automatic melody detection, tempo changes, and unprepared full-song cropping are not supported by this version. Melody notes must remain inside the excerpt. The 30–60-second target describes the demonstration/evaluation scope; the loader also accepts shorter fixtures for debugging.

```bash
python -m workstreams.taimoor.run --annotation path/to/reviewed_excerpt.json --output results/local/reviewed_excerpt --plots
```

To explore a different documented configuration without altering the recorded results:

```bash
python -m workstreams.taimoor.run --output results/local/continuity_check --continuity-weight 2.0
```

No configuration has been selected on real-song validation data yet. The command is an engineering exploration, not a completed advanced sensitivity study.

## Integration boundaries

| Teammate | Provisional handoff |
| --- | --- |
| Smit | Reviewed MIDI/annotation JSON and provenance. His pattern library can replace the small authored templates through the `Pattern` representation after agreeing an adapter. |
| Vinay | Selection traces and exported MIDI for independent descriptors/evaluation. The present local score does not call a classifier; a learned reranker needs a separate, reviewed interface and validation plan. |
| Abdullah | Transformed MIDI plus fixed tempo, length, and phrase markers for consistent SoundFont rendering and playback. |

The Python entry point is `arrange(song, target_style, method, weights)`, returning a `pretty_midi.PrettyMIDI` object and a JSON-serializable trace. `load_song(annotation_path)` prepares `song`; `write_midi(...)` preserves the excerpt endpoint and supplied phrase markers. This is a proposed initial contract, not a claim that the team has agreed it already.

## Evidence limits

- Every recorded input is generated by `fixtures.py`. The source-style names indicate authored presets, not independently annotated real genres.
- The verification fixtures share the generator and template assumptions with development fixtures. They are engineering verification cases, not an independent held-out real-music corpus.
- Four fixtures and 16 method runs establish reproducible execution and invariant checks only. They do not replace the planned 60-composition collection, held-out evaluation, or listening study.
- The arrangement library contains no GMD or Lakh data yet. No classifier, pretrained model, learned reranker, or text-to-audio generation has been trained or run.
- Transition cost is a hand-designed proxy. A lower cost is not evidence that listeners prefer an arrangement. All genre/coherence claims remain untested.
- Results were produced in the recorded Linux/Python environment with coding assistance. Taimoor's own local reproduction and musical review remain to be recorded.

The authoritative design specification remains the repository's root README. Detailed status, observed evidence, proposed advanced-objective refinements, and report text are in `docs/taimoor_progress.md`.
