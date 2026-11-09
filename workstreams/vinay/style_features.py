
import pretty_midi
import numpy as np


def load_midi(midi_path):
    # Load MIDI file
    midi = pretty_midi.PrettyMIDI(midi_path)
    return midi


def get_accompaniment_tracks(midi, melody_track_index):
    # Get all tracks except the melody track
    accompaniment_tracks = []

    for i in range(len(midi.instruments)):
        if i != melody_track_index:
            accompaniment_tracks.append(midi.instruments[i])

    return accompaniment_tracks


def calculate_note_density(midi, melody_track_index):
    # Count accompaniment notes per beat
    accompaniment_tracks = get_accompaniment_tracks(midi, melody_track_index)

    total_notes = 0

    for track in accompaniment_tracks:
        total_notes += len(track.notes)

    beats = midi.get_beats()

    if len(beats) < 2:
        return 0.0

    total_beats = (midi.get_end_time() - beats[0]) / np.median(np.diff(beats))

    if total_beats <= 0:
        return 0.0

    return float(total_notes / total_beats)


def calculate_average_note_duration(midi, melody_track_index):
    # Calculate average accompaniment note duration
    accompaniment_tracks = get_accompaniment_tracks(midi, melody_track_index)

    note_durations = []

    for track in accompaniment_tracks:
        for note in track.notes:
            duration = note.end - note.start
            note_durations.append(duration)

    if len(note_durations) == 0:
        return 0.0

    return float(np.mean(note_durations))


def calculate_average_polyphony(midi, melody_track_index):
    # Calculate average number of simultaneous accompaniment notes
    accompaniment_tracks = get_accompaniment_tracks(midi, melody_track_index)

    events = []

    for track in accompaniment_tracks:
        for note in track.notes:
            events.append((note.start, 1))
            events.append((note.end, -1))

    if len(events) == 0:
        return 0.0

    events.sort()

    active_notes = 0
    weighted_polyphony = 0
    previous_time = 0

    for time, change in events:
        duration = time - previous_time
        weighted_polyphony += active_notes * duration

        active_notes += change
        previous_time = time

    total_duration = midi.get_end_time()

    if total_duration <= 0:
        return 0.0

    return float(weighted_polyphony / total_duration)


def calculate_pitch_class_distribution(midi, melody_track_index):
    # Count pitch classes of non-drum accompaniment notes
    accompaniment_tracks = get_accompaniment_tracks(midi, melody_track_index)

    pitch_counts = np.zeros(12)

    for track in accompaniment_tracks:
        if track.is_drum:
            continue

        for note in track.notes:
            pitch_class = note.pitch % 12
            pitch_counts[pitch_class] += 1

    total_notes = np.sum(pitch_counts)

    if total_notes > 0:
        pitch_counts = pitch_counts / total_notes

    return pitch_counts


def calculate_onset_position_histogram(midi, melody_track_index):
    # Count note onsets at different positions within a beat
    accompaniment_tracks = get_accompaniment_tracks(midi, melody_track_index)

    beats = midi.get_beats()
    onset_counts = np.zeros(4)

    if len(beats) < 2:
        return onset_counts

    for track in accompaniment_tracks:
        for note in track.notes:
            beat_index = np.searchsorted(beats, note.start, side="right") - 1

            if beat_index < 0:
                continue

            if beat_index < len(beats) - 1:
                beat_duration = beats[beat_index + 1] - beats[beat_index]
            else:
                beat_duration = beats[-1] - beats[-2]

            if beat_duration <= 0:
                continue

            position = (note.start - beats[beat_index]) / beat_duration
            position = position % 1

            bin_index = min(int(position * 4), 3)
            onset_counts[bin_index] += 1

    total_onsets = np.sum(onset_counts)

    if total_onsets > 0:
        onset_counts = onset_counts / total_onsets

    return onset_counts


def calculate_offbeat_activity(midi, melody_track_index):
    # Calculate proportion of notes starting away from main beats
    accompaniment_tracks = get_accompaniment_tracks(midi, melody_track_index)

    beats = midi.get_beats()

    if len(beats) < 2:
        return 0.0

    beat_duration = np.median(np.diff(beats))

    total_notes = 0
    offbeat_notes = 0

    for track in accompaniment_tracks:
        for note in track.notes:
            nearest_beat = np.min(np.abs(beats - note.start))

            total_notes += 1

            if nearest_beat > 0.1 * beat_duration:
                offbeat_notes += 1

    if total_notes == 0:
        return 0.0

    return float(offbeat_notes / total_notes)


def calculate_bass_intervals(midi, melody_track_index):
    # Calculate average melodic interval in the bass
    accompaniment_tracks = get_accompaniment_tracks(midi, melody_track_index)

    bass_tracks = []

    for track in accompaniment_tracks:
        if track.is_drum:
            continue

        # General MIDI bass programs are 32 to 39
        if 32 <= track.program <= 39:
            bass_tracks.append(track)

    intervals = []

    for track in bass_tracks:
        notes = sorted(track.notes, key=lambda note: note.start)

        for i in range(1, len(notes)):
            interval = abs(notes[i].pitch - notes[i - 1].pitch)
            intervals.append(interval)

    if len(intervals) == 0:
        return 0.0

    return float(np.mean(intervals))


def extract_style_features(midi, melody_track_index):
    # Extract all accompaniment style features
    features = {}

    features["note_density"] = calculate_note_density(
        midi, melody_track_index
    )

    features["average_note_duration"] = calculate_average_note_duration(
        midi, melody_track_index
    )

    features["average_polyphony"] = calculate_average_polyphony(
        midi, melody_track_index
    )

    features["offbeat_activity"] = calculate_offbeat_activity(
        midi, melody_track_index
    )

    features["average_bass_interval"] = calculate_bass_intervals(
        midi, melody_track_index
    )

    onset_histogram = calculate_onset_position_histogram(
        midi, melody_track_index
    )

    for i in range(4):
        features[f"onset_position_{i}"] = float(onset_histogram[i])

    pitch_distribution = calculate_pitch_class_distribution(
        midi, melody_track_index
    )

    for i in range(12):
        features[f"pitch_class_{i}"] = float(pitch_distribution[i])

    return features
