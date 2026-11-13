# Audio-based assessment — automated, not human listening

The frozen arranger was not modified or retuned. This is a post hoc, independently pretrained audio-model check of the rendered WAV files.
CLAP similarities are not calibrated probabilities or validated 1–5 listening scores. Human coherence and recognizability ratings remain unfilled.

## Source/reference checks

| Development source | Folder label | Top of 10 genre prompts | Jazz/Rock choice | Jazz minus Rock cosine |
| --- | --- | --- | --- | ---: |
| jazz_Cest_si_bon | jazz | pop | jazz | 0.1665 |
| jazz_Feels_So_Good | jazz | jazz | jazz | 0.1441 |
| rock_Bad_Medicine | rock | pop | jazz | 0.0099 |
| rock_Sweet_Child_O_Mine | rock | jazz | jazz | 0.0239 |

Agreement with the four development-folder labels: **2/4** for the forced Jazz/Rock choice. This very small check is not a validated accuracy estimate; folders themselves are not independently re-labelled.

## Additional artist-labelled audio references

A post hoc sanity check used 12-second excerpts of Kevin MacLeod's *Hot Swing* (artist genre: Jazz) and *Rock on Chicago* (artist genre: Rock), both CC BY 4.0. CLAP selected the matching genre for both clips. These two examples were not used for arranger tuning, prompt selection or the original 44-clip model assessment.

The contrast with 2/4 agreement on project development sources is consistent with a mismatch involving the synthesized arrangements or their inherited genre labels. It does not establish the cause. The model is therefore **not used to fill final genre ratings for the project**. It remains a diagnostic audio-based measurement.

## Held-out output summaries

| Method | Top-of-10 matches target | Jazz/Rock choice matches target | Mean target-minus-opposite cosine | Mean source-to-output target-margin change |
| --- | ---: | ---: | ---: | ---: |
| instrument_only | 1/8 | 4/8 | 0.0045 | 0.0672 |
| fixed | 4/8 | 4/8 | 0.0232 | 0.0859 |
| adaptive | 4/8 | 5/8 | 0.0444 | 0.1071 |
| no_continuity | 3/8 | 4/8 | 0.0209 | 0.0837 |

## Per-output machine assessments

| Excerpt | Version | Model top genre | Jazz/Rock choice | Target-minus-opposite cosine | Melody events | Human coherence |
| --- | --- | --- | --- | ---: | --- | --- |
| Excerpt_01 | A | jazz | jazz | -0.2324 | pass | not collected |
| Excerpt_01 | B | jazz | jazz | -0.2394 | pass | not collected |
| Excerpt_01 | C | jazz | jazz | -0.2324 | pass | not collected |
| Excerpt_01 | D | jazz | jazz | -0.2324 | pass | not collected |
| Excerpt_02 | A | pop | jazz | -0.1660 | pass | not collected |
| Excerpt_02 | B | pop | rock | 0.0495 | pass | not collected |
| Excerpt_02 | C | pop | jazz | -0.1660 | pass | not collected |
| Excerpt_02 | D | pop | rock | 0.0143 | pass | not collected |
| Excerpt_03 | A | jazz | jazz | -0.1651 | pass | not collected |
| Excerpt_03 | B | pop | jazz | -0.0762 | pass | not collected |
| Excerpt_03 | C | jazz | jazz | -0.1490 | pass | not collected |
| Excerpt_03 | D | jazz | jazz | -0.1660 | pass | not collected |
| Excerpt_04 | A | jazz | jazz | -0.2058 | pass | not collected |
| Excerpt_04 | B | jazz | jazz | -0.2067 | pass | not collected |
| Excerpt_04 | C | jazz | jazz | -0.1143 | pass | not collected |
| Excerpt_04 | D | jazz | jazz | -0.2067 | pass | not collected |
| Excerpt_05 | A | jazz | jazz | 0.2501 | pass | not collected |
| Excerpt_05 | B | jazz | jazz | 0.2432 | pass | not collected |
| Excerpt_05 | C | jazz | jazz | 0.1892 | pass | not collected |
| Excerpt_05 | D | jazz | jazz | 0.2555 | pass | not collected |
| Excerpt_06 | A | jazz | jazz | 0.2941 | pass | not collected |
| Excerpt_06 | B | pop | jazz | 0.1469 | pass | not collected |
| Excerpt_06 | C | jazz | jazz | 0.2941 | pass | not collected |
| Excerpt_06 | D | jazz | jazz | 0.2941 | pass | not collected |
| Excerpt_07 | A | electronic | jazz | 0.1357 | pass | not collected |
| Excerpt_07 | B | electronic | jazz | 0.1424 | pass | not collected |
| Excerpt_07 | C | jazz | jazz | 0.1824 | pass | not collected |
| Excerpt_07 | D | jazz | jazz | 0.1824 | pass | not collected |
| Excerpt_08 | A | jazz | jazz | 0.2247 | pass | not collected |
| Excerpt_08 | B | pop | rock | -0.0555 | pass | not collected |
| Excerpt_08 | C | jazz | jazz | 0.2352 | pass | not collected |
| Excerpt_08 | D | jazz | jazz | 0.2247 | pass | not collected |

## Interpretation limits

- The model receives decoded waveforms only. It is separate from the arranger, its local scoring function and Vinay's symbolic descriptor proxy.
- Prompts, model revision and deterministic windows were fixed before project-audio inference. No prompt selection based on favourable outputs was performed.
- It is a quantized ONNX conversion of a general audio-text model. Its behaviour on General MIDI SoundFont synthesis is not independently validated.
- A forced two-genre choice always chooses Jazz or Rock, even when neither fits. Read it alongside the top-of-10 genre and raw margins.
- Source-to-output audio-embedding similarity is a global audio measurement, not a melody-recognizability rating.
- A similarity increase supports only model-based style evidence. It does not establish musical coherence, original-song recognizability or human preference.
- No listener identities, ratings, consent records or human observations have been generated.
- Prompt-template and segment-level scores are retained to expose instability. Small-sample counts should remain exploratory.

Model: https://huggingface.co/Xenova/clap-htsat-unfused ; original: https://huggingface.co/laion/clap-htsat-unfused .
Method: Wu et al., Large-scale Contrastive Language-Audio Pretraining with Feature Fusion and Keyword-to-Caption Augmentation, ICASSP 2023 (arXiv:2211.06687).
