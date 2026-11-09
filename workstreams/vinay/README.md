
# Style Modelling and Evaluation

CSC 575 - Cross-Genre Song Transformer

## Objective 1: Symbolic Style Representation

### PI1: Accompaniment Feature Extraction

This module extracts numerical features from MIDI accompaniment tracks to represent musical characteristics useful for Jazz and Rock style classification.

The melody track is excluded from feature extraction because the project aims to preserve the original melody while transforming the accompaniment.

### Implemented Features

| Feature | Description |
|---|---|
| Note density | Number of accompaniment notes per beat |
| Average note duration | Average duration of accompaniment notes in seconds |
| Average polyphony | Time-weighted average number of simultaneous accompaniment notes |
| Offbeat activity | Proportion of notes starting away from the main beats |
| Average bass interval | Average absolute pitch difference between consecutive bass notes |
| Onset-position histogram | Distribution of note onsets across four positions within a beat |
| Pitch-class distribution | Distribution of the 12 pitch classes in non-drum accompaniment |

A total of 21 numerical features are extracted.

### Implementation

- `style_features.py`: MIDI loading and feature extraction
- `test_style_features.py`: Synthetic MIDI fixtures and validation tests

Libraries used:
- pretty_midi
- NumPy

### Testing

Five synthetic tests were implemented:

1. Basic feature calculations
2. Offbeat activity
3. Overlapping notes and polyphony
4. Empty accompaniment
5. Melody exclusion

All five tests passed.

Run the tests from the repository root:

```powershell
python workstreams/vinay/test_style_features.py
```

### Assumptions and Limitations

- MIDI excerpts are expected to have a steady tempo, consistent with the project scope.
- The melody track index must be provided.
- Bass tracks are identified using General MIDI bass programs 32–39.
- Instrument program IDs are not included as classifier features.
- Offbeat activity is a simple rhythmic measure, not a complete syncopation measure.
- Note density and polyphony are measured across the selected excerpt duration.
- Current validation uses synthetic MIDI examples. Testing on real Jazz and Rock compositions is still required.

### Next Steps

- Validate features on the prepared MIDI dataset.
- Train a lightweight Jazz/Rock classifier using the training split.
- Compare at least two classifiers using validation data.
- Evaluate the selected model on held-out compositions.
