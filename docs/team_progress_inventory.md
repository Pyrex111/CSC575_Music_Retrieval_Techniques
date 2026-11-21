# Team progress records and handoffs

Repository inspection: 20 November 2026. All five remote branches and both pull
requests were checked, including complete recursive trees. A missing report in
Git does not establish that a teammate has not written or submitted one elsewhere.

| Member | Progress report found in Git | Available implementation and evidence |
| --- | --- | --- |
| Taimoor Shahzad | [Individual PDF](CSC575_Taimoor_Shahzad_Progress_Report.pdf) and [indicator/status notes](taimoor_progress.md) | Arrangement and comparative experiments on `taimoor/arranger-progress`; PDF checkpoint `5225a40364a250e90d8170ca45bf3966768c8283`. |
| Abdullah Shah | [Markdown progress record](https://github.com/Pyrex111/CSC575_Music_Retrieval_Techniques/blob/98510f50b262683e227a09b4017788e85800e93a/docs/abdullah_progress.md); no individual PDF located | Renderer, tests, and results for 17 synthetic-fixture WAVs. His record identifies playback/export integration as the next milestone. Branch `abdullah/audio-rendering`, revision `98510f50b262683e227a09b4017788e85800e93a`. |
| Vinay Kumar Devarakonda | No standalone progress report or PDF located; an [implementation README](https://github.com/Pyrex111/CSC575_Music_Retrieval_Techniques/blob/dcf7a4218243606e79055212830e08f4bfd9ff55/workstreams/vinay/README.md) is available | Feature extraction, classifier comparison, ranking, preservation, listening, and reporting code. The branch contains no saved trained model, classifier metrics, or listener responses. Its README describes fewer modules than the branch actually contains. Branch `vinay/style-evaluation`, revision `dcf7a4218243606e79055212830e08f4bfd9ff55`; PR #2 is open. |
| Smit Amin | No standalone progress report, status document, or PDF located | Dataset and excerpt manifests, 60 cropped MIDI/annotation pairs, inspection/cropping/chord-estimation scripts. Latest revision `ac9eb64673a4c6cfa086acbda5296f302dbf9ee9`, message `added chord detection`. Chord/phrase annotations explicitly say automatic and not manually reviewed. |

`main` remains at `2295649a2e3d6f47a9adebfceae9c243a9fda517` and contains only
the design README. PR #1 is draft; PR #2 is open. No team branch or PR was merged
as part of this inspection. Team work must be inspected on its own branch.

## Current handoff findings

The [new integration checkpoint](../results/taimoor_handoff/README.md) records:

- 60 prepared excerpts, with 30 train / 10 validation / 20 test assignments and
  30 excerpts in each source genre. These are the supplied split assignments,
  not a newly approved final protocol.
- The unmodified arranger loader accepts 45/60 original crops. Its remaining
  length failures are resolved in separate copies by normalizing terminal
  end-of-track messages. Every other absolute MIDI event and annotation byte
  is preserved; source files are unchanged.
- All 60 inputs load after that handoff normalization. Forty-six crops contain
  a terminal marker one tick beyond the annotated endpoint; the adapter also
  pads shorter track endpoints to the common excerpt endpoint.
- A composition-name group crosses train/validation: `jazz_015`
  (`The_Girl_From_Ipanema_Garota_de_Ipanema_.1`) and `jazz_020`
  (`The_Girl_From_Ipanema_Garota_de_Ipanema_`). This requires grouping review.
- Five current test compositions were in the earlier pilot: `rock_021` (Bad
  Medicine), `rock_023` (TNT), `jazz_022` (Feels So Good), `jazz_023` (La Vie en
  rose), and `jazz_026` (Light Years). They must not be presented as previously
  untouched final test compositions. All twelve earlier pilot compositions
  occur somewhere in the new collection.
- Artist fields are blank for all 60 records. Chord/phrase review, source
  attribution/licence review, and artist/alternate-version grouping are not
  recorded as completed in the supplied handoff.
- The classifier CSV adapter supplies Vinay's field names, uses the excerpt's
  melody index, and maps `val` to `validation`. Vinay's unmodified loader
  correctly rejects the candidate CSV because the composition group spans two
  splits. No classifier was trained to work around that rejection.
- Thirty training compositions produce 120/120 conditions passing the
  arranger checks and independent raw-event audit. This is a training-only
  execution check with earlier-pilot settings, not a final musical evaluation.

## Remaining work by dependency

1. **Input review and split decision:** Smit should confirm melody choices,
   review chord maps and phrase boundaries, resolve the duplicate composition,
   and complete provenance/artist metadata. Agree a grouped final split that
   discloses prior pilot exposure. No composition has been silently moved or
   relabelled by Taimoor's adapter.
2. **Independent evaluation handoff:** after the split is agreed, Vinay can
   consume the adapter CSV, compare classifiers using training/validation only,
   and document reliability and instrument controls. Model scores should remain
   supporting evidence unless their reliability on this domain is established.
3. **Taimoor's remaining implementation/experiments:** connect an agreed learned
   reranker to the same candidate library/constraints; predefine the broader
   weight/robustness study; freeze choices before final test comparisons. The
   current training check supplies integration evidence, not completion of
   those advanced indicators.
4. **Rendering and listening:** Abdullah's renderer can consume the final matched
   exports. Playback/export integration and actual method-anonymized listener
   responses remain to be completed. Existing blank forms and machine scores
   do not count as human ratings.
5. **Final reporting:** report per-composition outcomes, failures, limitations,
   and individual attribution after evaluation. Keep the submitted November 12
   progress PDF as its dated snapshot rather than silently rewriting its results.

Please obtain Smit's and Vinay's individual progress reports if they exist
outside Git, and Abdullah's PDF if a formal report was submitted. Their
implementation branches are enough to start integration but cannot establish
what their individual submitted reports claim.
