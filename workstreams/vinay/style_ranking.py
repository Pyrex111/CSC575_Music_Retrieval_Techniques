
import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
import pretty_midi

from style_features import extract_style_features
from style_classifier import FEATURE_NAMES


def calculate_style_score(model, features, target_genre):
    target_genre = target_genre.lower()

    if target_genre not in model.classes_:
        raise ValueError(f"Unknown target genre: {target_genre}")

    feature_values = pd.DataFrame(
        [{name: features[name] for name in FEATURE_NAMES}]
    )

    probabilities = model.predict_proba(feature_values)
    genre_index = list(model.classes_).index(target_genre)

    return float(probabilities[0][genre_index])


def rank_candidates(model, candidates, target_genre):
    results = []

    for candidate in candidates:
        midi = pretty_midi.PrettyMIDI(candidate["midi_path"])

        features = extract_style_features(
            midi,
            melody_track_index=candidate.get("melody_track_index", 0),
        )

        score = calculate_style_score(
            model,
            features,
            target_genre,
        )

        results.append({
            "candidate_id": candidate["candidate_id"],
            "midi_path": candidate["midi_path"],
            "target_genre": target_genre.lower(),
            "style_score": score,
        })

    results.sort(
        key=lambda item: item["style_score"],
        reverse=True,
    )

    for rank, result in enumerate(results, start=1):
        result["rank"] = rank

    return results


def save_ranking(results, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as file:
        json.dump(results, file, indent=4)

    print(f"Ranking saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path")
    parser.add_argument("candidates_json")
    parser.add_argument("target_genre", choices=["jazz", "rock"])
    parser.add_argument(
        "--output",
        default="workstreams/vinay/results/candidate_ranking.json",
    )
    args = parser.parse_args()

    model = joblib.load(args.model_path)

    with open(args.candidates_json) as file:
        candidates = json.load(file)

    results = rank_candidates(model, candidates, args.target_genre)

    print("\nCandidate ranking:")
    for result in results:
        print(
            f"{result['rank']}. {result['candidate_id']} "
            f"- {result['style_score']:.4f}"
        )

    save_ranking(results, args.output)


if __name__ == "__main__":
    main()
