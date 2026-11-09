
"""
CSC 575 - Cross-Genre Song Transformer

Vinay - Objective 2, PI2

Generate a method-anonymized, balanced listening study
for matched B0/B1/M arrangements.

Input manifest columns:
    composition_id
    target_genre
    method
    audio_path

Optional column:
    source_audio_path

Outputs:
    public_trials.csv
    private_trial_key.csv
    response_template.csv
    questionnaire.json
    study_metadata.json

The private key must never be distributed to listeners.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


METHODS = ("B0", "B1", "M")

RATING_QUESTIONS = {
    "style_fit": (
        "How well does this arrangement match "
        "the requested target genre?"
    ),
    "source_recognizability": (
        "How recognizable is the original musical "
        "material in this arrangement?"
    ),
    "musical_coherence": (
        "How musically coherent and natural "
        "does this arrangement sound?"
    ),
}

RATING_SCALE = {
    1: "Very poor",
    2: "Poor",
    3: "Moderate",
    4: "Good",
    5: "Excellent",
}


def make_identifier(*values):
    text = "|".join(str(value) for value in values)

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:12]


def load_manifest(manifest_path):
    manifest_path = Path(manifest_path)

    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Manifest not found: {manifest_path}"
        )

    data = pd.read_csv(manifest_path)

    required = {
        "composition_id",
        "target_genre",
        "method",
        "audio_path",
    }

    missing = required - set(data.columns)

    if missing:
        raise ValueError(
            f"Missing columns: {sorted(missing)}"
        )

    if data.empty:
        raise ValueError("Listening manifest is empty.")

    for column in required:
        if data[column].isna().any():
            raise ValueError(
                f"Missing values in column: {column}"
            )

        data[column] = (
            data[column].astype(str).str.strip()
        )

        if (data[column] == "").any():
            raise ValueError(
                f"Blank values in column: {column}"
            )

    if not data["method"].isin(METHODS).all():
        raise ValueError(
            "Methods must be B0, B1, or M."
        )

    keys = [
        "composition_id",
        "target_genre",
        "method",
    ]

    if data.duplicated(keys).any():
        raise ValueError(
            "Duplicate composition/genre/method rows."
        )

    if data["audio_path"].duplicated().any():
        raise ValueError(
            "Each arrangement must have a distinct "
            "audio path."
        )

    grouped = data.groupby(
        ["composition_id", "target_genre"]
    )

    for group_key, group in grouped:
        methods = set(group["method"])

        if methods != set(METHODS):
            raise ValueError(
                f"Incomplete B0/B1/M group: {group_key}"
            )

    if "source_audio_path" not in data.columns:
        data["source_audio_path"] = None

    for group_key, group in grouped:
        source_paths = (
            group["source_audio_path"]
            .dropna()
            .astype(str)
            .str.strip()
        )

        source_paths = source_paths[
            source_paths != ""
        ]

        if len(set(source_paths)) > 1:
            raise ValueError(
                f"Conflicting source audio: {group_key}"
            )

    return data


def balanced_method_orders():
    """
    All six permutations of three methods.

    Across each complete block of six participants,
    each method appears equally often in each
    presentation position.
    """
    return [
        ("B0", "B1", "M"),
        ("B1", "M", "B0"),
        ("M", "B0", "B1"),
        ("B0", "M", "B1"),
        ("M", "B1", "B0"),
        ("B1", "B0", "M"),
    ]


def create_listening_trials(
    manifest,
    participant_count=12,
    seed=42,
):
    if participant_count < 1:
        raise ValueError(
            "Participant count must be positive."
        )

    rng = np.random.default_rng(seed)

    group_columns = [
        "composition_id",
        "target_genre",
    ]

    groups = list(
        manifest.groupby(
            group_columns,
            sort=True,
        )
    )

    method_orders = balanced_method_orders()

    # Shuffle the six order assignments once per
    # composition group. Repeat the balanced cycle
    # for additional participants.
    group_orders = {}

    for group_key, _ in groups:
        order_indices = np.arange(
            len(method_orders)
        )

        rng.shuffle(order_indices)

        group_orders[group_key] = order_indices

    public_rows = []
    private_rows = []
    response_rows = []

    for participant_index in range(
        participant_count
    ):
        participant_id = (
            f"P{participant_index + 1:03d}"
        )

        group_indices = rng.permutation(
            len(groups)
        )

        trial_number = 0

        for group_index in group_indices:
            group_key, group = groups[
                int(group_index)
            ]

            composition_id, target_genre = (
                group_key
            )

            cycle_position = (
                participant_index
                % len(method_orders)
            )

            order_index = group_orders[
                group_key
            ][cycle_position]

            method_order = method_orders[
                int(order_index)
            ]

            group_lookup = {
                row["method"]: row
                for _, row in group.iterrows()
            }

            source_values = (
                group["source_audio_path"]
                .dropna()
                .astype(str)
                .str.strip()
            )

            source_values = source_values[
                source_values != ""
            ]

            source_audio = (
                source_values.iloc[0]
                if len(source_values)
                else None
            )

            group_id = make_identifier(
                composition_id,
                target_genre,
            )

            for position, method in enumerate(
                method_order,
                start=1,
            ):
                trial_number += 1

                candidate = group_lookup[
                    method
                ]

                trial_id = make_identifier(
                    participant_id,
                    group_id,
                    method,
                    seed,
                )

                public_rows.append({
                    "participant_id":
                        participant_id,
                    "trial_number":
                        trial_number,
                    "trial_id":
                        trial_id,
                    "group_id":
                        group_id,
                    "target_genre":
                        target_genre,
                    "presentation_position":
                        position,
                    "source_audio_path":
                        source_audio,
                    "audio_path":
                        candidate["audio_path"],
                })

                private_rows.append({
                    "participant_id":
                        participant_id,
                    "trial_id":
                        trial_id,
                    "composition_id":
                        composition_id,
                    "target_genre":
                        target_genre,
                    "method":
                        method,
                    "group_id":
                        group_id,
                })

                response_rows.append({
                    "participant_id":
                        participant_id,
                    "trial_id":
                        trial_id,
                    "style_fit":
                        None,
                    "source_recognizability":
                        None,
                    "musical_coherence":
                        None,
                })

    return (
        pd.DataFrame(public_rows),
        pd.DataFrame(private_rows),
        pd.DataFrame(response_rows),
    )


def create_questionnaire():
    return {
        "title": (
            "Cross-Genre Song Transformer "
            "- Listening Evaluation"
        ),
        "instructions": [
            (
                "Listen to the original source "
                "excerpt first."
            ),
            (
                "Listen to each transformed "
                "arrangement carefully."
            ),
            (
                "Rate each arrangement independently "
                "using the three questions."
            ),
            (
                "Do not attempt to identify the "
                "arrangement method."
            ),
            (
                "You may replay the audio before "
                "submitting your ratings."
            ),
        ],
        "rating_scale": RATING_SCALE,
        "questions": [
            {
                "id": question_id,
                "question": question,
                "minimum": 1,
                "maximum": 5,
                "required": True,
            }
            for question_id, question
            in RATING_QUESTIONS.items()
        ],
        "participant_metadata": [
            {
                "id": "musical_experience",
                "question": (
                    "How would you describe "
                    "your musical experience?"
                ),
                "options": [
                    "None",
                    "Beginner",
                    "Intermediate",
                    "Advanced",
                ],
            }
        ],
    }


def validate_trial_balance(
    public_trials,
    private_key,
):
    merged = public_trials.merge(
        private_key[
            [
                "participant_id",
                "trial_id",
                "method",
            ]
        ],
        on=[
            "participant_id",
            "trial_id",
        ],
        validate="one_to_one",
    )

    balance = (
        merged.groupby(
            [
                "group_id",
                "presentation_position",
                "method",
            ]
        )
        .size()
        .reset_index(name="count")
    )

    # With participant counts divisible by six,
    # all methods should occur equally often at
    # every position for every composition group.
    participant_count = (
        merged["participant_id"].nunique()
    )

    if participant_count % 6 == 0:
        counts = balance["count"]

        if counts.nunique() != 1:
            raise ValueError(
                "Balanced trial validation failed."
            )

    return balance


def save_listening_study(
    public_trials,
    private_key,
    response_template,
    questionnaire,
    balance,
    output_directory,
    seed,
    participant_count,
):
    output_directory = Path(
        output_directory
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    public_trials.to_csv(
        output_directory
        / "public_trials.csv",
        index=False,
    )

    private_key.to_csv(
        output_directory
        / "private_trial_key.csv",
        index=False,
    )

    response_template.to_csv(
        output_directory
        / "response_template.csv",
        index=False,
    )

    balance.to_csv(
        output_directory
        / "trial_balance.csv",
        index=False,
    )

    with (
        output_directory
        / "questionnaire.json"
    ).open("w", encoding="utf-8") as file:
        json.dump(
            questionnaire,
            file,
            indent=4,
        )

    metadata = {
        "seed": seed,
        "participant_count":
            participant_count,
        "method_count":
            len(METHODS),
        "trial_count":
            len(public_trials),
        "rating_questions":
            list(RATING_QUESTIONS),
        "balanced_cycle_size": 6,
        "fully_balanced": (
            participant_count % 6 == 0
        ),
        "notes": [
            (
                "Keep the private trial key "
                "separate from participants."
            ),
            (
                "Audio filenames and delivery "
                "interfaces must not reveal "
                "method identities."
            ),
            (
                "Partial six-person blocks "
                "are not guaranteed to be "
                "perfectly balanced."
            ),
        ],
    }

    with (
        output_directory
        / "study_metadata.json"
    ).open("w", encoding="utf-8") as file:
        json.dump(
            metadata,
            file,
            indent=4,
        )

    print(
        "Listening study generated successfully."
    )

    print(
        f"Participants: {participant_count}"
    )

    print(
        f"Trials: {len(public_trials)}"
    )

    print(
        f"Output: {output_directory}"
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "manifest",
        help="CSV with matched B0/B1/M audio.",
    )

    parser.add_argument(
        "--participants",
        type=int,
        default=12,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    parser.add_argument(
        "--output",
        default=(
            "workstreams/vinay/results/"
            "listening_study"
        ),
    )

    args = parser.parse_args()

    manifest = load_manifest(
        args.manifest
    )

    (
        public_trials,
        private_key,
        response_template,
    ) = create_listening_trials(
        manifest,
        participant_count=args.participants,
        seed=args.seed,
    )

    balance = validate_trial_balance(
        public_trials,
        private_key,
    )

    questionnaire = create_questionnaire()

    save_listening_study(
        public_trials,
        private_key,
        response_template,
        questionnaire,
        balance,
        args.output,
        args.seed,
        args.participants,
    )


if __name__ == "__main__":
    main()
