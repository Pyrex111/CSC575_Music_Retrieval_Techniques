
import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
import pretty_midi
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from style_features import extract_style_features


FEATURE_NAMES = [
    "note_density",
    "average_note_duration",
    "average_polyphony",
    "offbeat_activity",
    "average_bass_interval",
] + [f"onset_position_{i}" for i in range(4)] + [
    f"pitch_class_{i}" for i in range(12)
]

REQUIRED_COLUMNS = [
    "midi_path",
    "composition_id",
    "genre",
    "split",
]


def load_dataset(csv_path):
    data = pd.read_csv(csv_path)

    missing = [
        column for column in REQUIRED_COLUMNS
        if column not in data.columns
    ]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    data = data.copy()

    if data[REQUIRED_COLUMNS].isna().any().any():
        raise ValueError("Dataset contains missing required values.")

    data["genre"] = data["genre"].astype(str).str.strip().str.lower()
    data["split"] = data["split"].astype(str).str.strip().str.lower()

    if not data["genre"].isin(["jazz", "rock"]).all():
        raise ValueError("Genre must be Jazz or Rock.")

    if not data["split"].isin(["train", "validation", "test"]).all():
        raise ValueError("Split must be train, validation, or test.")

    for split in ["train", "validation", "test"]:
        if split not in data["split"].values:
            raise ValueError(f"Missing {split} split.")

    composition_splits = data.groupby("composition_id")["split"].nunique()

    if (composition_splits > 1).any():
        raise ValueError(
            "The same composition appears in multiple splits."
        )

    return data


def build_feature_table(data, dataset_directory):
    rows = []
    dataset_directory = Path(dataset_directory)

    for _, item in data.iterrows():
        midi_path = Path(item["midi_path"])

        if not midi_path.is_absolute():
            midi_path = dataset_directory / midi_path

        melody_index = int(item.get("melody_track_index", 0))

        # Load the MIDI file as a PrettyMIDI object.
        midi = pretty_midi.PrettyMIDI(str(midi_path))

        # Extract accompaniment style descriptors.
        features = extract_style_features(
            midi,
            melody_track_index=melody_index,
        )

        row = {
            "midi_path": str(midi_path),
            "composition_id": item["composition_id"],
            "genre": item["genre"],
            "split": item["split"],
        }

        row.update(features)
        rows.append(row)

    feature_table = pd.DataFrame(rows)

    missing_features = [
        feature for feature in FEATURE_NAMES
        if feature not in feature_table.columns
    ]

    if missing_features:
        raise ValueError(
            f"Missing extracted features: {missing_features}"
        )

    return feature_table


def create_models():
    return {
        "logistic_regression": Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(
                max_iter=1000,
                random_state=42,
            )),
        ]),
        "random_forest": RandomForestClassifier(
            n_estimators=100,
            random_state=42,
            class_weight="balanced",
        ),
    }


def train_and_select_model(feature_table):
    train = feature_table[feature_table["split"] == "train"]
    validation = feature_table[feature_table["split"] == "validation"]
    test = feature_table[feature_table["split"] == "test"]

    x_train = train[FEATURE_NAMES]
    y_train = train["genre"]

    x_validation = validation[FEATURE_NAMES]
    y_validation = validation["genre"]

    if y_train.nunique() != 2:
        raise ValueError(
            "Training data must contain both Jazz and Rock."
        )

    models = create_models()
    validation_results = {}

    for name, model in models.items():
        model.fit(x_train, y_train)

        predictions = model.predict(x_validation)

        score = f1_score(
            y_validation,
            predictions,
            average="macro",
            zero_division=0,
        )

        validation_results[name] = float(score)

        print(
            f"{name}: validation macro-F1 = {score:.4f}"
        )

    best_name = max(
        validation_results,
        key=validation_results.get,
    )

    best_model = models[best_name]

    print(f"\nSelected model: {best_name}")

    test_predictions = best_model.predict(
        test[FEATURE_NAMES]
    )

    test_score = f1_score(
        test["genre"],
        test_predictions,
        average="macro",
        zero_division=0,
    )

    print(f"\nHeld-out test macro-F1: {test_score:.4f}")

    print("\nClassification report:")
    print(classification_report(
        test["genre"],
        test_predictions,
        labels=["jazz", "rock"],
        zero_division=0,
    ))

    print("Confusion matrix (Jazz, Rock):")
    print(confusion_matrix(
        test["genre"],
        test_predictions,
        labels=["jazz", "rock"],
    ))

    errors = test[
        ["midi_path", "composition_id", "genre"]
    ].copy()

    errors["predicted_genre"] = test_predictions

    errors["correct"] = (
        errors["genre"] == errors["predicted_genre"]
    )

    metrics = {
        "selected_model": best_name,
        "validation_macro_f1": validation_results,
        "test_macro_f1": float(test_score),
        "test_compositions": int(
            test["composition_id"].nunique()
        ),
        "test_examples": int(len(test)),
    }

    return best_model, metrics, errors


def save_results(model, metrics, errors, output_directory):
    output_directory = Path(output_directory)

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        model,
        output_directory / "style_classifier.joblib",
    )

    with open(
        output_directory / "metrics.json",
        "w",
    ) as file:
        json.dump(metrics, file, indent=4)

    errors.to_csv(
        output_directory / "test_predictions.csv",
        index=False,
    )

    print(f"\nResults saved to: {output_directory}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("dataset_csv")

    parser.add_argument(
        "--output",
        default="workstreams/vinay/results",
    )

    args = parser.parse_args()

    csv_path = Path(args.dataset_csv).resolve()

    data = load_dataset(csv_path)

    feature_table = build_feature_table(
        data,
        csv_path.parent,
    )

    output_directory = Path(args.output)

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    feature_table.to_csv(
        output_directory / "extracted_features.csv",
        index=False,
    )

    model, metrics, errors = train_and_select_model(
        feature_table
    )

    save_results(
        model,
        metrics,
        errors,
        output_directory,
    )


if __name__ == "__main__":
    main()
