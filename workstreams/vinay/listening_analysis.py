import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


METHODS = ("B0", "B1", "M")

QUESTIONS = (
    "style_fit",
    "source_recognizability",
    "musical_coherence",
)

COMPARISONS = (
    ("B0", "B1"),
    ("B0", "M"),
    ("B1", "M"),
)


def load_study_data(responses_path, private_key_path):
    responses = pd.read_csv(
        responses_path,
        dtype={
            "participant_id": str,
            "trial_id": str,
        },
    )

    private_key = pd.read_csv(
        private_key_path,
        dtype={
            "participant_id": str,
            "trial_id": str,
            "composition_id": str,
            "target_genre": str,
            "method": str,
        },
    )

    response_columns = {
        "participant_id",
        "trial_id",
        *QUESTIONS,
    }

    key_columns = {
        "participant_id",
        "trial_id",
        "composition_id",
        "target_genre",
        "method",
    }

    missing_responses = (
        response_columns - set(responses.columns)
    )

    missing_key = (
        key_columns - set(private_key.columns)
    )

    if missing_responses:
        raise ValueError(
            "Missing response columns: "
            f"{sorted(missing_responses)}"
        )

    if missing_key:
        raise ValueError(
            "Missing private-key columns: "
            f"{sorted(missing_key)}"
        )

    if responses.empty or private_key.empty:
        raise ValueError(
            "Responses and private key cannot be empty."
        )

    identifiers = ["participant_id", "trial_id"]

    for name, frame in (
        ("responses", responses),
        ("private key", private_key),
    ):
        if frame[identifiers].isna().any().any():
            raise ValueError(
                f"Missing participant/trial IDs in {name}."
            )

        for column in identifiers:
            frame[column] = (
                frame[column].astype(str).str.strip()
            )

            if (frame[column] == "").any():
                raise ValueError(
                    f"Blank {column} in {name}."
                )

        if frame.duplicated(identifiers).any():
            raise ValueError(
                f"Duplicate participant/trial IDs in {name}."
            )

    for column in (
        "composition_id",
        "target_genre",
        "method",
    ):
        if private_key[column].isna().any():
            raise ValueError(
                f"Missing {column} in private key."
            )

        private_key[column] = (
            private_key[column].astype(str).str.strip()
        )

        if (private_key[column] == "").any():
            raise ValueError(
                f"Blank {column} in private key."
            )

    if not private_key["method"].isin(METHODS).all():
        raise ValueError(
            "Private key contains unknown methods."
        )

    for question in QUESTIONS:
        responses[question] = pd.to_numeric(
            responses[question],
            errors="raise",
        )

        values = responses[question].dropna()

        if not values.between(1, 5).all():
            raise ValueError(
                f"{question} must be between 1 and 5."
            )

        if not (values == values.round()).all():
            raise ValueError(
                f"{question} must use integer ratings."
            )

    merged = responses.merge(
        private_key,
        on=identifiers,
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    if (merged["_merge"] != "both").any():
        raise ValueError(
            "Some responses have no private-key match."
        )

    merged = merged.drop(columns="_merge")

    group_columns = [
        "participant_id",
        "composition_id",
        "target_genre",
        "method",
    ]

    if merged.duplicated(group_columns).any():
        raise ValueError(
            "Duplicate participant/composition/method ratings."
        )

    return merged, private_key


def build_coverage(ratings, private_key):
    expected = (
        private_key.groupby("participant_id")
        .size()
        .rename("expected_trials")
    )

    received = (
        ratings.groupby("participant_id")
        .size()
        .rename("received_trials")
    )

    complete = (
        ratings.assign(
            fully_rated=ratings[
                list(QUESTIONS)
            ].notna().all(axis=1)
        )
        .groupby("participant_id")["fully_rated"]
        .sum()
        .rename("fully_rated_trials")
    )

    coverage = pd.concat(
        [expected, received, complete],
        axis=1,
    ).fillna(0)

    for column in coverage.columns:
        coverage[column] = (
            coverage[column].astype(int)
        )

    coverage["missing_trials"] = (
        coverage["expected_trials"]
        - coverage["received_trials"]
    )

    coverage["incomplete_trials"] = (
        coverage["received_trials"]
        - coverage["fully_rated_trials"]
    )

    return coverage.reset_index()


def prepare_question_data(ratings, question):
    data = ratings[
        [
            "participant_id",
            "composition_id",
            "target_genre",
            "method",
            question,
        ]
    ].dropna(subset=[question]).copy()

    data = data.rename(
        columns={question: "rating"}
    )

    # Composition and transfer direction together
    # identify the matched musical example.
    data["composition_group"] = (
        data["composition_id"]
        + "|"
        + data["target_genre"]
    )

    return data


def clustered_bootstrap_means(
    data,
    methods,
    bootstrap_iterations,
    rng,
):
    """
    Resample participants and composition groups
    independently, with replacement.

    Repeated selections are represented by weights.
    Each selected participant/composition intersection
    receives the product of its sampling weights.
    """
    participants = np.array(
        sorted(data["participant_id"].unique())
    )

    compositions = np.array(
        sorted(data["composition_group"].unique())
    )

    if (
        len(participants) < 2
        or len(compositions) < 2
    ):
        return np.empty(
            (0, len(methods)),
            dtype=float,
        )

    participant_index = {
        value: index
        for index, value in enumerate(participants)
    }

    composition_index = {
        value: index
        for index, value in enumerate(compositions)
    }

    method_index = {
        value: index
        for index, value in enumerate(methods)
    }

    p_idx = data["participant_id"].map(
        participant_index
    ).to_numpy(dtype=int)

    c_idx = data["composition_group"].map(
        composition_index
    ).to_numpy(dtype=int)

    m_idx = data["method"].map(
        method_index
    ).to_numpy(dtype=int)

    values = data["rating"].to_numpy(
        dtype=float
    )

    samples = np.full(
        (bootstrap_iterations, len(methods)),
        np.nan,
    )

    for iteration in range(
        bootstrap_iterations
    ):
        sampled_p = rng.integers(
            len(participants),
            size=len(participants),
        )

        sampled_c = rng.integers(
            len(compositions),
            size=len(compositions),
        )

        p_weights = np.bincount(
            sampled_p,
            minlength=len(participants),
        )

        c_weights = np.bincount(
            sampled_c,
            minlength=len(compositions),
        )

        weights = (
            p_weights[p_idx]
            * c_weights[c_idx]
        )

        totals = np.bincount(
            m_idx,
            weights=weights * values,
            minlength=len(methods),
        )

        counts = np.bincount(
            m_idx,
            weights=weights,
            minlength=len(methods),
        )

        valid = counts > 0

        samples[
            iteration,
            valid,
        ] = totals[valid] / counts[valid]

    return samples


def confidence_interval(values):
    values = np.asarray(
        values,
        dtype=float,
    )

    values = values[
        np.isfinite(values)
    ]

    if len(values) == 0:
        return None, None, 0

    lower, upper = np.percentile(
        values,
        [2.5, 97.5],
    )

    return (
        float(lower),
        float(upper),
        int(len(values)),
    )


def summarize_methods(
    ratings,
    bootstrap_iterations,
    rng,
):
    rows = []

    for question in QUESTIONS:
        data = prepare_question_data(
            ratings,
            question,
        )

        if data.empty:
            for method in METHODS:
                rows.append({
                    "question": question,
                    "method": method,
                    "rating_count": 0,
                    "participant_count": 0,
                    "composition_count": 0,
                    "mean_rating": None,
                    "median_rating": None,
                    "ci_lower": None,
                    "ci_upper": None,
                    "valid_bootstrap_samples": 0,
                })

            continue

        bootstrap = clustered_bootstrap_means(
            data,
            METHODS,
            bootstrap_iterations,
            rng,
        )

        for method_index, method in enumerate(
            METHODS
        ):
            subset = data[
                data["method"] == method
            ]

            lower, upper, valid_samples = (
                confidence_interval(
                    bootstrap[:, method_index]
                )
                if len(bootstrap)
                else (None, None, 0)
            )

            rows.append({
                "question": question,
                "method": method,
                "rating_count": int(
                    len(subset)
                ),
                "participant_count": int(
                    subset["participant_id"].nunique()
                ),
                "composition_count": int(
                    subset["composition_group"].nunique()
                ),
                "mean_rating": (
                    float(subset["rating"].mean())
                    if len(subset)
                    else None
                ),
                "median_rating": (
                    float(subset["rating"].median())
                    if len(subset)
                    else None
                ),
                "ci_lower": lower,
                "ci_upper": upper,
                "valid_bootstrap_samples":
                    valid_samples,
            })

    return pd.DataFrame(rows)


def summarize_paired_comparisons(
    ratings,
    bootstrap_iterations,
    rng,
):
    rows = []

    for question in QUESTIONS:
        data = prepare_question_data(
            ratings,
            question,
        )

        if data.empty:
            continue

        paired = data.pivot(
            index=[
                "participant_id",
                "composition_group",
            ],
            columns="method",
            values="rating",
        ).reindex(columns=list(METHODS))

        for first, second in COMPARISONS:
            complete = (
                paired[[first, second]]
                .dropna()
                .reset_index()
            )

            differences = (
                complete[second]
                - complete[first]
            )

            # Bootstrap paired differences rather than
            # independently bootstrapping method means.
            difference_data = (
                complete[
                    [
                        "participant_id",
                        "composition_group",
                    ]
                ].copy()
            )

            difference_data["method"] = "difference"
            difference_data["rating"] = (
                differences.to_numpy(dtype=float)
            )

            bootstrap = (
                clustered_bootstrap_means(
                    difference_data,
                    ["difference"],
                    bootstrap_iterations,
                    rng,
                )
                if not complete.empty
                else np.empty((0, 1))
            )

            lower, upper, valid_samples = (
                confidence_interval(
                    bootstrap[:, 0]
                )
                if len(bootstrap)
                else (None, None, 0)
            )

            rows.append({
                "question": question,
                "method_1": first,
                "method_2": second,
                "paired_rating_count": int(
                    len(complete)
                ),
                "participant_count": int(
                    complete["participant_id"].nunique()
                ),
                "composition_count": int(
                    complete["composition_group"].nunique()
                ),
                "mean_difference": (
                    float(differences.mean())
                    if len(differences)
                    else None
                ),
                "median_difference": (
                    float(differences.median())
                    if len(differences)
                    else None
                ),
                "ci_lower": lower,
                "ci_upper": upper,
                "valid_bootstrap_samples":
                    valid_samples,
            })

    return pd.DataFrame(rows)


def analyze_listening_study(
    responses_path,
    private_key_path,
    output_directory,
    bootstrap_iterations=2000,
    seed=42,
):
    if bootstrap_iterations < 1:
        raise ValueError(
            "Bootstrap iterations must be positive."
        )

    ratings, private_key = load_study_data(
        responses_path,
        private_key_path,
    )

    coverage = build_coverage(
        ratings,
        private_key,
    )

    rng = np.random.default_rng(seed)

    method_summary = summarize_methods(
        ratings,
        bootstrap_iterations,
        rng,
    )

    paired_comparisons = (
        summarize_paired_comparisons(
            ratings,
            bootstrap_iterations,
            rng,
        )
    )

    output_directory = Path(
        output_directory
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    ratings.to_csv(
        output_directory
        / "validated_ratings.csv",
        index=False,
    )

    method_summary.to_csv(
        output_directory
        / "method_summary.csv",
        index=False,
    )

    paired_comparisons.to_csv(
        output_directory
        / "paired_comparisons.csv",
        index=False,
    )

    coverage.to_csv(
        output_directory
        / "participant_coverage.csv",
        index=False,
    )

    metadata = {
        "participant_count": int(
            ratings["participant_id"].nunique()
        ),
        "composition_count": int(
            ratings[
                ["composition_id", "target_genre"]
            ].drop_duplicates().shape[0]
        ),
        "response_row_count": int(
            len(ratings)
        ),
        "expected_trial_count": int(
            len(private_key)
        ),
        "fully_rated_trial_count": int(
            ratings[
                list(QUESTIONS)
            ].notna().all(axis=1).sum()
        ),
        "bootstrap_iterations":
            bootstrap_iterations,
        "random_seed": seed,
        "confidence_level": 0.95,
        "interval_method": (
            "Two-way participant/composition "
            "clustered percentile bootstrap"
        ),
        "difference_definition": (
            "method_2 minus method_1"
        ),
        "limitations": [
            (
                "Intervals are exploratory and may "
                "be unstable with small samples."
            ),
            (
                "Bootstrap uncertainty is not "
                "estimated with fewer than two "
                "participants or composition groups."
            ),
            (
                "Missing ratings are excluded "
                "per question; coverage is reported."
            ),
            (
                "No formal hypothesis tests or "
                "multiple-testing corrections "
                "are performed."
            ),
            (
                "Study recruitment and exclusion "
                "reasons must be documented "
                "separately."
            ),
        ],
    }

    with (
        output_directory
        / "analysis_metadata.json"
    ).open("w", encoding="utf-8") as file:
        json.dump(
            metadata,
            file,
            indent=4,
        )

    print("Listening analysis completed.")
    print(
        "Participants with responses:",
        metadata["participant_count"],
    )
    print(
        "Complete trial ratings:",
        metadata["fully_rated_trial_count"],
    )
    print("Results saved to:", output_directory)

    return (
        method_summary,
        paired_comparisons,
        coverage,
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "responses",
        help="Completed participant response CSV.",
    )

    parser.add_argument(
        "private_key",
        help="Private trial-to-method mapping CSV.",
    )

    parser.add_argument(
        "--output",
        default=(
            "workstreams/vinay/results/"
            "listening_analysis"
        ),
    )

    parser.add_argument(
        "--bootstrap",
        type=int,
        default=2000,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    args = parser.parse_args()

    analyze_listening_study(
        args.responses,
        args.private_key,
        args.output,
        bootstrap_iterations=args.bootstrap,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
