
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.inspection import permutation_importance
from sklearn.metrics import f1_score

from style_classifier import FEATURE_NAMES


FEATURE_GROUPS = {
    "rhythm": [
        "note_density",
        "offbeat_activity",
        "onset_position_0",
        "onset_position_1",
        "onset_position_2",
        "onset_position_3",
    ],
    "duration_polyphony": [
        "average_note_duration",
        "average_polyphony",
    ],
    "bass": [
        "average_bass_interval",
    ],
    "pitch_class": [
        f"pitch_class_{i}" for i in range(12)
    ],
}


def check_feature_columns(data):
    missing = [name for name in FEATURE_NAMES if name not in data.columns]

    if missing:
        raise ValueError(f"Missing features: {missing}")

    if any("program" in name.lower() or "instrument" in name.lower()
           for name in FEATURE_NAMES):
        raise ValueError("Instrument identity is included in classifier features.")

    if data[FEATURE_NAMES].isna().any().any():
        raise ValueError("Feature table contains missing values.")


def analyze_errors(data, model):
    test = data[data["split"] == "test"].copy()

    if test.empty:
        raise ValueError("No test examples available.")

    test["predicted_genre"] = model.predict(test[FEATURE_NAMES])
    test["correct"] = test["genre"] == test["predicted_genre"]

    errors = test.loc[
        ~test["correct"],
        ["midi_path", "composition_id", "genre", "predicted_genre"]
    ].copy()

    print(f"Test examples: {len(test)}")
    print(f"Misclassified examples: {len(errors)}")

    return errors


def analyze_feature_importance(data, model):
    test = data[data["split"] == "test"]

    if test.empty:
        raise ValueError("No test examples available.")

    result = permutation_importance(
        model,
        test[FEATURE_NAMES],
        test["genre"],
        scoring="f1_macro",
        n_repeats=10,
        random_state=42,
    )

    importance = pd.DataFrame({
        "feature": FEATURE_NAMES,
        "importance_mean": result.importances_mean,
        "importance_std": result.importances_std,
    })

    return importance.sort_values(
        "importance_mean", ascending=False
    ).reset_index(drop=True)


def analyze_feature_groups(data, model):
    train = data[data["split"] == "train"]
    validation = data[data["split"] == "validation"]

    if train.empty or validation.empty:
        raise ValueError("Training and validation examples are required.")

    baseline_predictions = model.predict(validation[FEATURE_NAMES])
    baseline_score = f1_score(
        validation["genre"],
        baseline_predictions,
        average="macro",
        zero_division=0,
    )

    rows = []

    for group_name, excluded_features in FEATURE_GROUPS.items():
        remaining = [
            feature for feature in FEATURE_NAMES
            if feature not in excluded_features
        ]

        reduced_model = clone(model)
        reduced_model.fit(
            train[remaining],
            train["genre"],
        )

        predictions = reduced_model.predict(validation[remaining])
        score = f1_score(
            validation["genre"],
            predictions,
            average="macro",
            zero_division=0,
        )

        rows.append({
            "excluded_group": group_name,
            "baseline_macro_f1": float(baseline_score),
            "reduced_macro_f1": float(score),
            "score_difference": float(baseline_score - score),
        })

    return pd.DataFrame(rows)


def save_analysis(errors, importance, groups, output_directory):
    output_directory.mkdir(parents=True, exist_ok=True)

    errors.to_csv(output_directory / "classification_errors.csv", index=False)
    importance.to_csv(output_directory / "feature_importance.csv", index=False)
    groups.to_csv(output_directory / "feature_group_ablation.csv", index=False)

    summary = {
        "test_errors": int(len(errors)),
        "feature_count": len(FEATURE_NAMES),
        "excluded_instrument_program_ids": True,
    }

    with open(output_directory / "analysis_summary.json", "w") as file:
        json.dump(summary, file, indent=4)

    print(f"Analysis saved to: {output_directory}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features_csv")
    parser.add_argument("model_path")
    parser.add_argument("--output", default="workstreams/vinay/results")
    args = parser.parse_args()

    data = pd.read_csv(args.features_csv)
    model = joblib.load(args.model_path)

    check_feature_columns(data)

    errors = analyze_errors(data, model)
    importance = analyze_feature_importance(data, model)
    groups = analyze_feature_groups(data, model)

    print("\nTop 5 important features:")
    print(importance.head(5).to_string(index=False))

    print("\nFeature group ablation:")
    print(groups.to_string(index=False))

    save_analysis(errors, importance, groups, Path(args.output))


if __name__ == "__main__":
    main()
