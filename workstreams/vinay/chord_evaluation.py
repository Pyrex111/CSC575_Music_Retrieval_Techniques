
import argparse
import json
from pathlib import Path

import numpy as np


TIME_TOLERANCE = 0.01

NOTE_NAMES = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "A#": 10,
    "B": 11,
}

FLAT_TO_SHARP = {
    "Db": "C#",
    "Eb": "D#",
    "Gb": "F#",
    "Ab": "G#",
    "Bb": "A#",
}


def normalize_chord(chord):
    chord = str(chord).strip()

    if chord.upper() in ["N", "NC", "NO_CHORD"]:
        return "N"

    if not chord:
        raise ValueError("Chord label cannot be empty.")

    root = chord[0].upper()
    remaining = chord[1:]

    if remaining and remaining[0] in ["#", "b"]:
        root += remaining[0]
        remaining = remaining[1:]

    root = FLAT_TO_SHARP.get(root, root)

    if root not in NOTE_NAMES:
        raise ValueError(f"Invalid chord root: {chord}")

    quality = remaining.strip().lower()

    quality_aliases = {
        "": "maj",
        "major": "maj",
        "maj": "maj",
        "m": "min",
        "min": "min",
        "minor": "min",
        "7": "7",
        "maj7": "maj7",
        "major7": "maj7",
        "m7": "min7",
        "min7": "min7",
        "minor7": "min7",
        "dim": "dim",
        "aug": "aug",
        "sus2": "sus2",
        "sus4": "sus4",
    }

    if quality not in quality_aliases:
        raise ValueError(f"Unsupported chord quality: {chord}")

    return f"{root}:{quality_aliases[quality]}"


def validate_chords(chords):
    validated = []

    for chord in chords:
        if not all(
            key in chord
            for key in ["start", "end", "label"]
        ):
            raise ValueError(
                "Each chord requires start, end, and label."
            )

        start = float(chord["start"])
        end = float(chord["end"])

        if not np.isfinite(start) or not np.isfinite(end):
            raise ValueError("Chord times must be finite.")

        if start < 0 or end <= start:
            raise ValueError("Invalid chord time interval.")

        validated.append({
            "start": start,
            "end": end,
            "label": normalize_chord(chord["label"]),
        })

    validated.sort(key=lambda item: (item["start"], item["end"]))

    for previous, current in zip(
        validated,
        validated[1:],
    ):
        if current["start"] < previous["end"] - TIME_TOLERANCE:
            raise ValueError("Chord annotations overlap.")

    return validated


def compare_chords(
    original_chords=None,
    transformed_chords=None,
    tolerance=TIME_TOLERANCE,
):
    if original_chords is None or transformed_chords is None:
        return {
            "chords_checked": False,
            "chords_preserved": None,
            "reason": "Chord annotations not available.",
        }

    original = validate_chords(original_chords)
    transformed = validate_chords(transformed_chords)

    same_count = len(original) == len(transformed)

    same_labels = same_count
    same_boundaries = same_count

    if same_count:
        for first, second in zip(original, transformed):
            if first["label"] != second["label"]:
                same_labels = False

            if not np.isclose(
                first["start"],
                second["start"],
                atol=tolerance,
                rtol=0,
            ):
                same_boundaries = False

            if not np.isclose(
                first["end"],
                second["end"],
                atol=tolerance,
                rtol=0,
            ):
                same_boundaries = False

    preserved = (
        same_count
        and same_labels
        and same_boundaries
    )

    return {
        "chords_checked": True,
        "original_chord_count": len(original),
        "transformed_chord_count": len(transformed),
        "same_chord_count": bool(same_count),
        "same_chord_labels": bool(same_labels),
        "same_chord_boundaries": bool(same_boundaries),
        "chords_preserved": bool(preserved),
    }


def save_chord_results(results, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as file:
        json.dump(results, file, indent=4)

    print(f"Chord results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("original_chords_json")
    parser.add_argument("transformed_chords_json")

    parser.add_argument(
        "--output",
        default="workstreams/vinay/results/chord_results.json",
    )

    args = parser.parse_args()

    with open(args.original_chords_json) as file:
        original_chords = json.load(file)

    with open(args.transformed_chords_json) as file:
        transformed_chords = json.load(file)

    results = compare_chords(
        original_chords,
        transformed_chords,
    )

    print("\nChord preservation evaluation:")
    print(json.dumps(results, indent=4))

    save_chord_results(results, args.output)


if __name__ == "__main__":
    main()
