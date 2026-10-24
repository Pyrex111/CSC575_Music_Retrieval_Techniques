# Cross-Genre Song Transformer

**CSC575 project design and requirements specification**  
**Team:** Smit Amin, Taimoor Shahzad, Vinay Kumar Devarakonda, and Abdullah Shah  
**Date:** October 2026

## Project description

Our project is a cross-genre song transformer. We will build a system that takes a 30–60-second instrumental MIDI excerpt and rearranges it between Jazz and Rock styles while preserving its main melody and phrase structure. The transformation will change the accompaniment instruments, basslines, drum patterns, chord voicings, and chord rhythms while retaining the original chord progression. The system will export transformed MIDI and playable audio.
We will compare our adaptive arrangement approach against instrument substitution and fixed-pattern templates to investigate the following question:
Does a melody-constrained, style-aware arrangement method produce a more recognizable target style than instrument substitution alone, while retaining the source melody and phrase layout?

## Team and responsibilities

Taimoor and Vinay, the graduate students, will lead algorithm design, modelling, controlled experiments, and interpretation. Smit and Abdullah will lead data preparation, baseline implementation, audio rendering, and the usable demonstration. All members will contribute literature review, documentation, integration, and the final report.

| Member | Email | Primary responsibility | Main outputs |
| --- | --- | --- | --- |
| Smit Amin | smitamin@uvic.ca | MIDI preparation and baseline arrangement | Dataset manifest, annotations, validated parser, fixed-pattern baseline |
| Taimoor Shahzad | tshahzad@uvic.ca | Constrained arrangement and comparative experiments | Pattern adaptation, phrase-level selection, ablations, method analysis |
| Vinay Kumar Devarakonda | vinaykumardevarakon1@uvic.ca | Style modelling and evaluation | Descriptors, classifier comparison, preservation metrics, listening analysis |
| Abdullah Shah | abdullahshahoct@gmail.com | Audio rendering and system integration | MIDI-to-WAV pipeline, listening interface, reproducible demonstration |

## Scope and requirements

We will focus on approximately 30–60-second instrumental MIDI excerpts in 4/4 time with a steady tempo. Excerpts will begin and end at complete musical phrase boundaries. Shorter 8–16-bar examples will support early development. Users will manually select the melody track, and chord estimates and phrase boundaries will be reviewed during preparation. Ambiguous inputs will require correction or be excluded with a recorded reason.

- **What stays the same:** The melody’s pitches, note onsets and durations, overall tempo, chord progression, excerpt length, and phrase layout.
- **What can change:** The accompaniment instrumentation, drum grooves, bassline motion, chord rhythms, chord voicings, note density, and velocities.
- **What is outside the core scope:** Automatic verse–chorus detection, MP3/WAV audio input, vocal transformation, unrestricted genre coverage, studio-quality sound design, and large-model training.

| ID | Requirement | Verification |
| --- | --- | --- |
| FR1 | Load supported MIDI and expose tracks, tempo, metre, and duration. | Compare parsed data with inspected reference files. |
| FR2 | Allow melody-track and target-style selection. | Exercise both target styles and different melody tracks. |
| FR3 | Preserve melody pitches, onsets, and durations in beat coordinates. | Compare note events, allowing at most one source MIDI tick for serialization rounding. |
| FR4 | Preserve tempo, chord progression, bar count, and supplied phrase boundaries. | Compare arrangement metadata and the reviewed chord map. |
| FR5 | Change at least two accompaniment properties beyond instrumentation, such as drum rhythm, bass motion, or chord rhythm. | Inspect exported events and matched audio examples. |
| FR6 | Export transformed MIDI and playable WAV. | Reopen MIDI and verify successful rendering, finite samples, and nonzero audio. |
| FR7 | Provide source/transformed playback and downloads. | Complete the demonstration workflow. |
| FR8 | Save configuration, data IDs, applicable random seeds, and processing times. | Reproduce an example from its saved configuration. |

The core pipeline will run on CPU with documented dependencies and clear errors for unsupported files. Transformation and rendering time will be measured separately on a documented machine. Audio comparisons will use consistent synthesis and loudness settings.

## Proposed methodology

### Input representation

We will use `pretty_midi` [15] for MIDI manipulation and `music21` [16] to support harmonic analysis. The shared representation will store note events in beats, track roles, chord labels, bar boundaries, and phrase markers. The original melody events will be stored separately so that accompaniment changes cannot overwrite them. Chord estimates will be inspected and corrected where necessary; the amount of manual assistance will be reported.

### Baselines and adaptive arrangement

| Condition | Behaviour | Purpose |
| --- | --- | --- |
| B0: instrument substitution | Keep source notes and timing; change accompaniment instruments. | Establish what timbre changes alone achieve. |
| B1: fixed-pattern arrangement | Keep melody and harmony; apply predefined target-style drum, bass, and chord patterns. | Provide a functioning arrangement baseline. |
| M: adaptive arrangement | Apply the same preservation constraints; retrieve and adapt patterns using target style and phrase context. | Test the value of context-aware selection. |

B1 and M will use the same annotations, instrument palettes, and candidate library. For B1, a predefined pattern choice will be used; M will select from that library using musical context. This keeps the comparison focused on selection quality.

The library will combine training-split drum grooves from the Groove MIDI Dataset (GMD) [14] with team-authored bass and chord templates. Pitched templates will use chord-relative representations. Each pattern will record its provenance, style, metre, length, and usable tempo range.

The Rock preset will emphasize electric guitar/bass and backbeat-oriented drums. The Jazz preset will emphasize piano, acoustic bass, ride-cymbal patterns, and syncopated comping. These are limited arrangement presets rather than comprehensive definitions of either genre. Any swing adjustment will affect accompaniment timing only.

Taimoor will implement chord-aware pitch mapping and candidate scoring based on target-style descriptor distance, chord compatibility, instrument ranges, and transitions between patterns. Phrase-level selection, such as dynamic programming over a small candidate set, will favour continuity and related patterns at repeated phrases. Weights will be chosen using development data. Hard constraints will protect the melody and prevent invalid pitches, nonpositive durations, and accompaniment outside excerpt boundaries.

### Style modelling

Vinay will extract accompaniment descriptors including onset-position histograms, offbeat activity, note density, durations, bass intervals, pitch-class distributions, and polyphony. A logistic-regression classifier and a second lightweight model will be compared using training and validation data. Instrument program IDs will be excluded from the primary feature set to reduce reliance on instrumentation alone.

The core arranger will use transparent descriptor distances. A learned candidate reranker is an advanced achievement target. A model used to optimize output selection will not also count as independent evidence of improvement. Classifier scores will be interpreted alongside held-out classifier performance, symbolic measurements, and listening results.

### Existing model comparison

Groove2Groove [5] is a candidate pretrained comparison because it accepts content and style-reference MIDI. Its documented environment uses Python 3.6 and TensorFlow 1.x. We will time-box installation and inference checks in Week 1 and use a separate environment. If compatible inference is unavailable, we will document the blocker and complete the B0/B1/M comparison. Reproducing a large generative training pipeline is not required for the core system.

### Rendering and demonstration

Abdullah will render source and transformed MIDI with FluidSynth and a documented General MIDI SoundFont [18]. The same renderer, SoundFont, sample rate, and loudness procedure will be used across methods. A local Streamlit interface will support MIDI loading, melody and style selection, playback, and export, with input limitations and supplied annotations visible to the user.

## Datasets and preparation

| Source | Use | Main checks |
| --- | --- | --- |
| Lakh MIDI Dataset [13] | Candidate multitrack excerpts and reviewed genre examples. | Inspect file validity, melody tracks, metadata, genre labels, and alternate versions of the same composition. |
| Groove MIDI Dataset [14] | Style-labelled drum patterns. | Normalize drum mappings and restrict the arrangement library to training-split performances. This dataset does not supply complete songs. |
| Team-authored MIDI fixtures and pitched templates | Controlled preservation checks, chord adaptation, and demonstration examples. | Keep these separate from evidence about generalization to real source compositions. |
| Groove2Groove resources [5] | Compatible style references and pretrained comparison, if usable. | Check access, dependencies, terms, and input restrictions. |

The collection target is **60 distinct compositions**, balanced between the two source genres, with one phrase-aligned excerpt of approximately 30–60 seconds per composition: 30 training, 10 validation, and 20 held-out test compositions. Availability and annotation effort will be assessed in Week 1. Any necessary reduction will be recorded before fitting models or evaluating results.

The manifest will include source IDs, attribution, reviewed genre, melody-track index, chords, tempo, metre, crop boundaries, and split. Two members will review uncertain genre labels. Duplicates, alternate arrangements, and augmentations of one composition will remain in the same split. Artists will be separated where metadata and sample size permit. Test material will not enter model fitting, parameter selection, or the pattern library.

The Lakh and GMD websites state CC BY 4.0 distribution terms; Lakh also notes inconsistent individual MIDI authorship information. We will retain provenance and review redistribution conditions for selected files. Acquisition instructions and manifests will be published where source music cannot be redistributed. SoundFont terms will be documented separately.

## Evaluation

All methods will be compared on the same held-out inputs with both transfer directions represented. No paired target-genre recording is assumed to exist. Failed conversions and exclusions will be included in the results.

| Aspect | Measurement and interpretation |
| --- | --- |
| Melody preservation | Compare pitches, onsets, and durations with one-tick serialization tolerance. Since melody events are copied, this is an implementation check rather than learned content preservation. |
| Phrase layout and harmony | Check bar count, supplied phrase boundaries, and preservation of the reviewed chord progression. |
| Style evidence | Report classifier macro-F1 and confusion matrix on held-out reference music, then interpret target-style scores for generated arrangements cautiously. |
| Musical behaviour | Measure accompaniment density, onset distributions, range violations, bass/voicing jumps, and pattern repetition. Explain their musical implications. |
| Perceptual quality | Collect separate 1–5 ratings for target-style fit, source recognizability, and musical coherence. |
| Practical performance | Report conversion success rate, transformation time, rendering time, and hardware. |

MusPy [12] will support suitable symbolic descriptors, and `mir_eval` [17] will inform standardized note comparisons. Custom metrics will include definitions and units. Objective scores will complement rather than replace listening evaluation [10, 11].

We plan an exploratory listening study with approximately 8–12 volunteers outside the team, subject to course guidance. Eight balanced held-out excerpts will be compared under B0, B1, and M. Listeners will hear a source reference followed by method-anonymized outputs in randomized order. Recruitment, musical experience, exclusions, and deviations will be reported. If recruitment is insufficient, team listening will be labelled an internal pilot.

Vinay will analyze paired listener/composition results and retain these groupings in uncertainty estimates. Automated summaries will use composition-level observations. Taimoor will run ablations removing adaptive selection and continuity constraints. Feature controls will examine whether style evidence depends mainly on instrument identity. The limited dataset and volunteer sample will constrain the conclusions.

Success means delivering the supported MIDI-to-audio workflow, verifying preservation requirements, and completing a reproducible B0/B1/M comparison. Improved listener-rated style fit is the hypothesis being tested, not a guaranteed result.

## Tools and resources

| Tool | Purpose |
| --- | --- |
| Python, NumPy, pandas | Event processing, manifests, descriptors, and experiment summaries. |
| pretty_midi [15] and music21 [16] | MIDI input/output, note manipulation, and harmonic analysis. |
| MusPy [12] and mir_eval [17] | Symbolic descriptors and evaluation utilities. |
| scikit-learn | Lightweight classification and model comparison. |
| FluidSynth and a General MIDI SoundFont [18] | Consistent MIDI-to-WAV synthesis. |
| Streamlit | Local listening and export interface. |
| Git/GitHub, Jupyter, Matplotlib | Version control, analysis, documentation, and figures. |

The main implementation is CPU-capable. GPU access is not assumed. Package versions, renderer settings, and machine specifications will be recorded with the first working environment.

## Timeline

The implementation plan covers six weeks after design submission. Progress-report and final-report checkpoints will follow the official course calendar; their dates were not included in the supplied instructions.

| Period | Objectives | Deliverable | Leads |
| --- | --- | --- | --- |
| Design submission | Complete the specification, responsibilities, objectives, and bibliography. | Entire README submitted through Brightspace. | All |
| Week 1 | Review data availability, freeze corpus/splits, agree interfaces, test rendering, and assess pretrained compatibility. | Manifest, representation schema, source audio, feasibility findings. | Smit and Abdullah; graduate review |
| Week 2 | Implement B0/B1, preservation checks, and initial descriptors using short development fixtures. | Executable baselines and feature notebook. | Smit, Taimoor, Vinay |
| Week 3 | Implement adaptive selection and classifier comparison; connect playback/export. | M prototype and working interface supporting 30–60-second excerpts. | Taimoor, Vinay, Abdullah |
| Week 4 | Freeze parameters, run held-out comparisons and ablations, and pilot listening materials. | Reproducible outputs, automated results, listening protocol. | All |
| Week 5 | Conduct listening evaluation and analyze results and failures. | Tables, figures, and matched examples. | Vinay and Taimoor; team support |
| Week 6 | Complete integration, update the README, and prepare ISMIR-format reporting and demonstration. | Final code, reproducible examples, report, and presentation. | All |

Weekly meetings will review integration, achievement against indicators, and changes to scope or schedule.

## Related work

### Symbolic style transfer

Lu and Su [1] study homophonic music, separating a prominent melody from its accompaniment. This directly informs our decision to preserve a selected melody while modifying surrounding parts. Brunner et al. [2] use CycleGAN for unpaired symbolic genre transfer, addressing the absence of matched performances across genres. We address content preservation with explicit constraints rather than relying on cycle consistency.

MIDI-VAE [3] models multiple tracks, dynamics, and instrumentation, motivating transformations beyond pitch or instrument substitution. Cífka et al. [4] use synthetic aligned accompaniments for supervised style translation, illustrating the importance of defining content and style. Groove2Groove [5] extends this approach to one-shot accompaniment transfer and is our candidate pretrained comparison. Its resources do not replace our input annotation and preservation requirements.

METEOR [6] studies melody-aware, texture-controllable re-orchestration. It reinforces the value of separating melodic identity from accompaniment texture. Because re-orchestration alone does not establish a genre change, our evaluation will measure style fit separately from recognizability.

### Representation and structure

MusicVAE [7] uses hierarchical latent representations, while Music Transformer [8] uses relative attention to capture musical relationships over time. These works motivate phrase-level organization, although our proof of concept will retain supplied boundaries rather than train those architectures. Pop Music Transformer [9] emphasizes beat-based representation, informing our use of beat/bar coordinates for pattern adaptation and alignment.

### Evaluation and supporting tools

The Jazz Transformer study [10] examines generated music through listening and measurements of pitch, rhythm, harmony, and structure. Yang and Lerch [11] discuss the difficulty of evaluating generative music. Together, they support our use of multiple measurements and separate perceptual questions rather than a single quality score.

MusPy [12] provides symbolic processing and evaluation functions. Lakh [13] supplies candidate multitrack material, but requires file, annotation, and split validation. GMD [14] supplies expressive labelled drum performances for one component of our arrangement library. Finally, pretty_midi [15], music21 [16], mir_eval [17], and FluidSynth [18] provide established manipulation, analysis, measurement, and rendering components. Our contribution is their integration with a constrained adaptive arranger and a controlled evaluation.

## Individual objectives and performance indicators

Each member has two objectives and five indicators per objective: two basic, two expected, and one advanced. Basic indicators establish a functional foundation, expected indicators define the planned project contribution, and advanced indicators describe the highest achievement level each member will work toward. Progress at all three levels will be reported with supporting evidence.

## Smit Amin

### Objective 1: Prepare a documented and validated MIDI corpus

- **PI1 (basic):** Implement a loader that reports tracks, note counts, tempo, metre, and duration for at least five inspected MIDI files, and records malformed-file errors.
- **PI2 (basic):** Create a manifest with source IDs, attribution, melody-track selections, and crop boundaries for those files.
- **PI3 (expected):** Assemble the agreed corpus, record exclusions and genre reviews, and create composition-grouped training, validation, and test manifests with duplicate checks.
- **PI4 (expected):** Produce reviewed melody and chord annotations for the selected excerpts and summarize annotation corrections and data-quality issues.
- **PI5 (advanced):** Add a melody-track suggestion heuristic and evaluate its top-choice agreement with manually selected tracks, reporting ambiguity and failures.

### Objective 2: Implement reproducible baseline transformations

- **PI1 (basic):** Implement B0 for both target palettes while retaining source note events and timing.
- **PI2 (basic):** Create and document fixed drum, bass, and chord templates for B1 in the shared pattern format.
- **PI3 (expected):** Implement B1 with chord-aware pitch mapping and verified preservation of the selected melody and excerpt length.
- **PI4 (expected):** Run both baselines on the frozen held-out set and produce a reproducible table of success rates, runtimes, and detected event violations.
- **PI5 (advanced):** Compare two fixed-pattern variants per target style and explain how their rhythmic differences affect baseline output characteristics.

## Taimoor Shahzad

### Objective 1: Design and implement a melody-constrained adaptive arranger

- **PI1 (basic):** Define the arrangement representation and interfaces for melody events, chord maps, phrase boundaries, and accompaniment patterns, with worked examples.
- **PI2 (basic):** Implement chord-aware adaptation of candidate bass and chord patterns while protecting the melody and enforcing duration and pitch bounds.
- **PI3 (expected):** Implement target-style pattern retrieval using documented descriptor distances and harmony/register constraints; select parameters using development data only.
- **PI4 (expected):** Implement phrase-level candidate selection with transition penalties and repeated-phrase consistency, and generate 30–60-second arrangements for both target styles.
- **PI5 (advanced):** Integrate a learned candidate reranker or a compatible pretrained accompaniment model and compare it against the core adaptive method on matched inputs.

### Objective 2: Determine which arrangement choices contribute to transformation quality

- **PI1 (basic):** Define the research hypothesis and a matched B0/B1/M experiment, listing controlled factors and the outcomes being measured.
- **PI2 (basic):** Build an experiment runner that saves input IDs, configuration, method, seed where relevant, output paths, and processing times.
- **PI3 (expected):** Complete held-out comparisons across both transfer directions and analyze melody invariants, accompaniment changes, failures, and runtime.
- **PI4 (expected):** Run ablations removing adaptive selection and continuity constraints, analyze per-composition results, and relate findings to the observed musical outputs.
- **PI5 (advanced):** Conduct a sensitivity study of style-distance and continuity weights, using validation data for selection and reporting the trade-offs on the frozen final configuration.

## Vinay Kumar Devarakonda

### Objective 1: Develop and critically validate a symbolic style representation

- **PI1 (basic):** Implement and document accompaniment descriptors for rhythmic positions, density, duration, pitch usage, and polyphony.
- **PI2 (basic):** Fit a simple target-style classifier on the training split and verify that feature extraction and scaling do not use validation or test examples.
- **PI3 (expected):** Compare at least two lightweight classifiers using validation data, then report the selected model's held-out macro-F1 and confusion matrix.
- **PI4 (expected):** Analyze classification errors and feature dependence, including an instrument-identity control, and state when classifier evidence is too weak to support genre-transfer conclusions.
- **PI5 (advanced):** Develop a learned ranking score for Taimoor's candidate selector and evaluate its utility without using that same score as independent proof of transfer quality.

### Objective 2: Design a defensible evaluation of preservation and perceived style

- **PI1 (basic):** Define melody-event, bar-count, and phrase-boundary checks and validate them on fixtures with deliberately inserted errors.
- **PI2 (basic):** Design a method-anonymized listening questionnaire with separate style-fit, recognizability, and coherence questions and a balanced trial schedule.
- **PI3 (expected):** Run the agreed listening protocol where recruitment permits, document participant counts and exclusions, and report any deviation from the planned sample.
- **PI4 (expected):** Analyze paired listener and composition results with uncertainty estimates that preserve these groupings, and compare perceptual findings with symbolic and classifier evidence.
- **PI5 (advanced):** Investigate an additional generalization control, such as held-out drum performers or a separate compatible MIDI collection, and report changes in style evidence and output quality.

## Abdullah Shah

### Objective 1: Deliver consistent, playable audio outputs

- **PI1 (basic):** Install and document FluidSynth and a usable SoundFont, and render at least five reference MIDI excerpts to WAV.
- **PI2 (basic):** Implement a reusable rendering function with explicit sample rate, output path, error capture, and checks for nonempty finite audio.
- **PI3 (expected):** Integrate rendering with B0, B1, and M; use the same synthesis and documented loudness procedure for all comparison conditions.
- **PI4 (expected):** Validate rendering across the agreed demonstration set, report failures and rendering time, and document the renderer and SoundFont versions and terms.
- **PI5 (advanced):** Compare a second SoundFont on a small matched subset to assess whether conclusions are sensitive to the choice of instrument sounds.

### Objective 2: Build and validate the complete demonstration workflow

- **PI1 (basic):** Build an interface that loads supported MIDI files and exposes melody-track and target-style selections.
- **PI2 (basic):** Add source/transformed playback and MIDI/WAV download controls using the shared backend interfaces.
- **PI3 (expected):** Connect input analysis, arrangement, rendering, and configuration logging into one workflow with clear handling of unsupported inputs.
- **PI4 (expected):** Verify the workflow on the agreed demonstration examples in both directions, document setup and known limitations, and prepare reproducible demonstration instructions.
- **PI5 (advanced):** Add a phrase-aligned piano-roll comparison that highlights the preserved melody and changed accompaniment alongside audio playback.

## Risks and contingencies

| Risk | Response |
| --- | --- |
| Insufficient usable, genre-labelled MIDI | Freeze a smaller reviewed corpus in Week 1 and narrow conclusions accordingly. |
| Ambiguous melody or chords | Use explicit track selection and reviewed harmony; record assistance and unresolved exclusions. |
| Legacy pretrained dependencies | Time-box compatibility work and retain the independent B0/B1/M implementation. |
| Style evidence dominated by instrumentation | Keep B1/M palettes matched, control classifier features, and collect separate perceptual ratings. |
| Fixed melody limits stylistic flexibility | Report examples where accompaniment changes do not produce a convincing transformation. |
| Limited time or listening sample | Prioritize the complete core workflow and matched evaluation, and report achieved indicators and evidence limitations. |

## Deliverables and reporting

This entire README.md is the design submission. It will be maintained for the progress report and final implementation status. The repository will contain source code, setup instructions, manifests, experiment configurations, evaluation scripts, and redistributable demonstration outputs.

The final report will adapt the maintained text and results to ISMIR LaTeX format, identify completed and deferred work, document individual contributions, and distinguish reused software from team-developed methods.

## References

[1] W.-T. Lu and L. Su, “Transferring the Style of Homophonic Music Using Recurrent Neural Networks and Autoregressive Models,” in *Proceedings of ISMIR*, pp. 740–746, 2018. [Paper](https://ismir2018.ircam.fr/doc/pdfs/107_Paper.pdf).

[2] G. Brunner, Y. Wang, R. Wattenhofer, and S. Zhao, “Symbolic Music Genre Transfer with CycleGAN,” in *Proceedings of ICTAI*, 2018. [Author preprint](https://arxiv.org/abs/1809.07575).

[3] G. Brunner, A. Konrad, Y. Wang, and R. Wattenhofer, “MIDI-VAE: Modeling Dynamics and Instrumentation of Music with Applications to Style Transfer,” in *Proceedings of ISMIR*, pp. 747–754, 2018. [Author preprint](https://arxiv.org/abs/1809.07600).

[4] O. Cífka, U. Şimşekli, and G. Richard, “Supervised Symbolic Music Style Translation Using Synthetic Data,” in *Proceedings of ISMIR*, 2019. [Paper](https://archives.ismir.net/ismir2019/paper/000071.pdf). doi: 10.5281/zenodo.3527878.

[5] O. Cífka, U. Şimşekli, and G. Richard, “Groove2Groove: One-Shot Music Style Transfer with Supervision from Synthetic Data,” *IEEE/ACM Transactions on Audio, Speech, and Language Processing*, vol. 28, pp. 2638–2650, 2020. doi: 10.1109/TASLP.2020.3019642. [Author code and resources](https://github.com/cifkao/groove2groove).

[6] D.-V.-T. Le and Y.-H. Yang, “METEOR: Melody-aware Texture-controllable Symbolic Music Re-Orchestration via Transformer VAE,” in *Proceedings of IJCAI*, pp. 10126–10134, 2025. [Paper and bibliographic record](https://www.ijcai.org/proceedings/2025/1125). doi: 10.24963/ijcai.2025/1125.

[7] A. Roberts, J. Engel, C. Raffel, C. Hawthorne, and D. Eck, “A Hierarchical Latent Vector Model for Learning Long-Term Structure in Music,” in *Proceedings of ICML*, PMLR, vol. 80, pp. 4364–4373, 2018. [Paper](https://proceedings.mlr.press/v80/roberts18a.html).

[8] C.-Z. A. Huang et al., “Music Transformer: Generating Music with Long-Term Structure,” in *ICLR*, 2019. [Publication record](https://research.google/pubs/music-transformer-generating-music-with-long-term-structure/). [Author preprint](https://arxiv.org/abs/1809.04281).

[9] Y.-S. Huang and Y.-H. Yang, “Pop Music Transformer: Beat-based Modeling and Generation of Expressive Pop Piano Compositions,” in *Proceedings of ACM Multimedia*, 2020. [Author preprint](https://arxiv.org/abs/2002.00212).

[10] S.-L. Wu and Y.-H. Yang, “The Jazz Transformer on the Front Line: Exploring the Shortcomings of AI-composed Music through Quantitative Measures,” in *Proceedings of ISMIR*, pp. 142–149, 2020. [Paper](https://archives.ismir.net/ismir2020/paper/000339.pdf).

[11] L.-C. Yang and A. Lerch, “On the Evaluation of Generative Models in Music,” *Neural Computing and Applications*, vol. 32, pp. 4773–4784, 2020; first published online 2018. [Article](https://doi.org/10.1007/s00521-018-3849-7).

[12] H.-W. Dong, K. Chen, J. McAuley, and T. Berg-Kirkpatrick, “MusPy: A Toolkit for Symbolic Music Generation,” in *Proceedings of ISMIR*, 2020. [Paper record](https://zenodo.org/records/4245380).

[13] C. Raffel, *Learning-Based Methods for Comparing Sequences, with Applications to Audio-to-MIDI Alignment and Matching*, Ph.D. dissertation, Columbia University, 2016. [Associated Lakh MIDI Dataset, documentation, and dissertation citation](https://colinraffel.com/projects/lmd/).

[14] J. Gillick, A. Roberts, J. Engel, D. Eck, and D. Bamman, “Learning to Groove with Inverse Sequence Transformations,” in *Proceedings of ICML*, 2019. [Associated Groove MIDI Dataset and paper citation](https://magenta.tensorflow.org/datasets/groove).

[15] C. Raffel and D. P. W. Ellis, “Intuitive Analysis, Creation and Manipulation of MIDI Data with pretty_midi,” in *ISMIR Late Breaking and Demo Papers*, 2014. [Author software and citation](https://github.com/craffel/pretty-midi).

[16] M. S. Cuthbert and C. Ariza, “music21: A Toolkit for Computer-Aided Musicology and Symbolic Music Data,” in *Proceedings of ISMIR*, pp. 637–642, 2010. [MIT publication record](https://dspace.mit.edu/entities/publication/fc03dc19-5571-4bb2-b9f7-0cc1217512b2).

[17] C. Raffel, B. McFee, E. J. Humphrey, J. Salamon, O. Nieto, D. Liang, and D. P. W. Ellis, “mir_eval: A Transparent Implementation of Common MIR Metrics,” in *Proceedings of ISMIR*, pp. 367–372, 2014. [Paper](https://colinraffel.com/publications/ismir2014mir_eval.pdf).

[18] FluidSynth developers, “FluidSynth Documentation,” software documentation, accessed October 19, 2026. [Documentation](https://www.fluidsynth.org/documentation/).
