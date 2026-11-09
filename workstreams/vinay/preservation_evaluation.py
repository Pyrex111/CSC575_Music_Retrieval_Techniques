
import argparse
import json
from pathlib import Path

import numpy as np
import pretty_midi


TIME_TOLERANCE = 0.01
TEMPO_TOLERANCE = 0.01


def load_midi(midi_source):
    if isinstance(midi_source, pretty_midi.PrettyMIDI):
        return midi_source

    return pretty_midi.PrettyMIDI(str(midi_source))


def get_melody_notes(midi, melody_track_index=0):
    if not 0 <= melody_track_index < len(midi.instruments):
        raise ValueError("Invalid melody track index.")

    notes = midi.instruments[melody_track_index].notes

    return sorted(
        notes,
        key=lambda note: (
            note.start,
            note.pitch,
            note.end,
        ),
    )


def compare_melody(
    original,
    transformed,
    original_melody_index=0,
    transformed_melody_index=0,
    tolerance=TIME_TOLERANCE,
):
    original_notes = get_melody_notes(
        original,
        original_melody_index,
    )

    transformed_notes = get_melody_notes(
        transformed,
        transformed_melody_index,
    )

    same_note_count = (
        len(original_notes) == len(transformed_notes)
    )

    same_pitches = same_note_count
    same_onsets = same_note_count
    same_durations = same_note_count

    if same_note_count:
        for original_note, transformed_note in zip(
            original_notes,
            transformed_notes,
        ):
            if original_note.pitch != transformed_note.pitch:
                same_pitches = False

            if not np.isclose(
                original_note.start,
                transformed_note.start,
                atol=tolerance,
                rtol=0,
            ):
                same_onsets = False

            original_duration = (
                original_note.end - original_note.start
            )

            transformed_duration = (
                transformed_note.end - transformed_note.start
            )

            if not np.isclose(
                original_duration,
                transformed_duration,
                atol=tolerance,
                rtol=0,
            ):
                same_durations = False

    return {
        "original_note_count": len(original_notes),
        "transformed_note_count": len(transformed_notes),
        "same_note_count": bool(same_note_count),
        "same_pitches": bool(same_pitches),
        "same_onsets": bool(same_onsets),
        "same_durations": bool(same_durations),
        "melody_preserved": bool(
            same_note_count
            and same_pitches
            and same_onsets
            and same_durations
        ),
    }


def compare_tempo(original, transformed):
    original_times, original_tempos = (
        original.get_tempo_changes()
    )

    transformed_times, transformed_tempos = (
        transformed.get_tempo_changes()
    )

    same_count = (
        len(original_times) == len(transformed_times)
    )

    if same_count:
        same_times = bool(np.allclose(
            original_times,
            transformed_times,
            atol=TIME_TOLERANCE,
            rtol=0,
        ))

        same_tempos = bool(np.allclose(
            original_tempos,
            transformed_tempos,
            atol=TEMPO_TOLERANCE,
            rtol=0,
        ))
    else:
        same_times = False
        same_tempos = False

    return {
        "same_tempo_event_count": bool(same_count),
        "same_tempo_times": same_times,
        "same_tempo_values": same_tempos,
        "tempo_preserved": bool(
            same_count and same_times and same_tempos
        ),
    }


def get_bar_count(midi, end_time=None):
    if end_time is None:
        end_time = midi.get_end_time()

    if end_time <= 0:
        return 0

    beats = midi.get_beats()

    if len(beats) < 2:
        raise ValueError(
            "Cannot determine bar count from MIDI beats."
        )

    beat_length = float(np.median(np.diff(beats)))

    time_signatures = midi.time_signature_changes

    if time_signatures:
        signature = time_signatures[0]

        if any(
            item.numerator != signature.numerator
            or item.denominator != signature.denominator
            for item in time_signatures
        ):
            raise ValueError(
                "Changing time signatures are not supported."
            )

        beats_per_bar = (
            signature.numerator * 4 / signature.denominator
        )
    else:
        beats_per_bar = 4.0

    bar_length = beat_length * beats_per_bar

    return int(np.ceil(
        (end_time - TIME_TOLERANCE) / bar_length
    ))


def compare_bar_count(
    original,
    transformed,
    original_end_time=None,
    transformed_end_time=None,
):
    original_bars = get_bar_count(
        original,
        original_end_time,
    )

    transformed_bars = get_bar_count(
        transformed,
        transformed_end_time,
    )

    return {
        "original_bars": original_bars,
        "transformed_bars": transformed_bars,
        "bar_count_preserved": bool(
            original_bars == transformed_bars
        ),
    }


def compare_phrase_boundaries(
    original_boundaries=None,
    transformed_boundaries=None,
    tolerance=TIME_TOLERANCE,
):
    if (
        original_boundaries is None
        or transformed_boundaries is None
    ):
        return {
            "phrase_boundaries_checked": False,
            "phrase_boundaries_preserved": None,
        }

    original_boundaries = np.asarray(
        original_boundaries,
        dtype=float,
    )

    transformed_boundaries = np.asarray(
        transformed_boundaries,
        dtype=float,
    )

    same_boundaries = bool(
        original_boundaries.shape
        == transformed_boundaries.shape
        and np.allclose(
            original_boundaries,
            transformed_boundaries,
            atol=tolerance,
            rtol=0,
        )
    )

    return {
        "phrase_boundaries_checked": True,
        "phrase_boundaries_preserved": same_boundaries,
    }


def evaluate_preservation(
    original_midi,
    transformed_midi,
    original_melody_index=0,
    transformed_melody_index=0,
    original_phrase_boundaries=None,
    transformed_phrase_boundaries=None,
    original_end_time=None,
    transformed_end_time=None,
):
    original = load_midi(original_midi)
    transformed = load_midi(transformed_midi)

    melody_results = compare_melody(
        original,
        transformed,
        original_melody_index,
        transformed_melody_index,
    )

    tempo_results = compare_tempo(
        original,
        transformed,
    )

    bar_results = compare_bar_count(
        original,
        transformed,
        original_end_time,
        transformed_end_time,
    )

    phrase_results = compare_phrase_boundaries(
        original_phrase_boundaries,
        transformed_phrase_boundaries,
    )

    checks = [
        melody_results["melody_preserved"],
        tempo_results["tempo_preserved"],
        bar_results["bar_count_preserved"],
    ]

    if phrase_results["phrase_boundaries_checked"]:
        checks.append(
            phrase_results["phrase_boundaries_preserved"]
        )

    return {
        "melody": melody_results,
        "tempo": tempo_results,
        "bars": bar_results,
        "phrases": phrase_results,
        "overall_preserved": bool(all(checks)),
    }


def save_preservation_results(results, output_path):
    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(output_path, "w") as file:
        json.dump(results, file, indent=4)

    print(f"Preservation results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("original_midi")
    parser.add_argument("transformed_midi")

    parser.add_argument(
        "--original-melody-index",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--transformed-melody-index",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--output",
        default=(
            "workstreams/vinay/results/"
            "preservation_results.json"
        ),
    )

    args = parser.parse_args()

    results = evaluate_preservation(
        args.original_midi,
        args.transformed_midi,
        original_melody_index=args.original_melody_index,
        transformed_melody_index=args.transformed_melody_index,
    )

    print("\nPreservation evaluation:")
    print(json.dumps(results, indent=4))

    save_preservation_results(
        results,
        args.output,
    )


if __name__ == "__main__":
    main()
