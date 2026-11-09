
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


METHODS = ("B0", "B1", "M")

PRESERVATION_CHECKS = (
    "melody",
    "tempo",
    "bars",
    "phrases",
    "chords",
)


def load_json(path):
    if pd.isna(path) or str(path).strip() == "":
        return None

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Evaluation file not found: {path}"
        )

    with path.open(encoding="utf-8") as file:
        return json.load(file)


def resolve_path(value, base_directory):
    if pd.isna(value) or str(value).strip() == "":
        return None

    path = Path(str(value).strip())

    if not path.is_absolute():
        path = base_directory / path

    return path


def load_batch_manifest(manifest_path):
    manifest_path = Path(manifest_path)
    data = pd.read_csv(manifest_path)

    required = {
        "composition_id",
        "target_genre",
        "method",
    }

    missing = required - set(data.columns)

    if missing:
        raise ValueError(
            f"Missing manifest columns: {sorted(missing)}"
        )

    if data.empty:
        raise ValueError("Batch manifest is empty.")

    if data[list(required)].isna().any().any():
        raise ValueError(
            "Composition, genre, and method cannot be missing."
        )

    for column in required:
        data[column] = data[column].astype(str).str.strip()

    if (data[list(required)] == "").any().any():
        raise ValueError(
            "Composition, genre, and method cannot be blank."
        )

    invalid_methods = set(data["method"]) - set(METHODS)

    if invalid_methods:
        raise ValueError(
            f"Unknown methods: {sorted(invalid_methods)}"
        )

    if data.duplicated(
        ["composition_id", "target_genre", "method"]
    ).any():
        raise ValueError(
            "Duplicate composition/genre/method rows."
        )

    for column in (
        "preservation_path",
        "chord_path",
        "ranking_path",
    ):
        if column not in data.columns:
            data[column] = None

    return data, manifest_path.parent


def extract_preservation_checks(
    preservation,
    chords,
):
    checks = {
        check: None
        for check in PRESERVATION_CHECKS
    }

    if preservation is not None:
        checks["melody"] = preservation.get(
            "melody", {}
        ).get("melody_preserved")

        checks["tempo"] = preservation.get(
            "tempo", {}
        ).get("tempo_preserved")

        checks["bars"] = preservation.get(
            "bars", {}
        ).get("bar_count_preserved")

        phrase = preservation.get("phrases", {})

        if phrase.get("phrase_boundaries_checked"):
            checks["phrases"] = phrase.get(
                "phrase_boundaries_preserved"
            )

    if chords is not None and chords.get(
        "chords_checked"
    ):
        checks["chords"] = chords.get(
            "chords_preserved"
        )

    return checks


def extract_style_score(ranking, method):
    if ranking is None:
        return None

    if not isinstance(ranking, list):
        raise ValueError(
            "Ranking JSON must contain a list."
        )

    matching = [
        item for item in ranking
        if item.get("method") == method
    ]

    if len(matching) == 1:
        return matching[0].get("style_score")

    if len(matching) > 1:
        raise ValueError(
            f"Multiple ranking entries for method {method}."
        )

    if len(ranking) == 1:
        return ranking[0].get("style_score")

    return None


def build_batch_table(manifest, base_directory):
    rows = []

    for _, entry in manifest.iterrows():
        preservation = load_json(
            resolve_path(
                entry["preservation_path"],
                base_directory,
            )
        )

        chords = load_json(
            resolve_path(
                entry["chord_path"],
                base_directory,
            )
        )

        ranking = load_json(
            resolve_path(
                entry["ranking_path"],
                base_directory,
            )
        )

        checks = extract_preservation_checks(
            preservation,
            chords,
        )

        evaluated = [
            value for value in checks.values()
            if value is not None
        ]

        if not evaluated:
            overall = None
        elif any(value is False for value in evaluated):
            overall = False
        elif len(evaluated) == len(PRESERVATION_CHECKS):
            overall = True
        else:
            overall = None

        row = {
            "composition_id": entry["composition_id"],
            "target_genre": entry["target_genre"],
            "method": entry["method"],
            "style_score": extract_style_score(
                ranking,
                entry["method"],
            ),
            "overall_preserved": overall,
            "evaluated_checks": len(evaluated),
            "missing_checks": (
                len(PRESERVATION_CHECKS) - len(evaluated)
            ),
        }

        for check, result in checks.items():
            row[f"{check}_preserved"] = result

        rows.append(row)

    return pd.DataFrame(rows)


def summarize_methods(batch_table):
    rows = []

    for method in METHODS:
        subset = batch_table[
            batch_table["method"] == method
        ]

        scores = pd.to_numeric(
            subset["style_score"],
            errors="coerce",
        ).dropna()

        preservation = subset[
            "overall_preserved"
        ].dropna()

        rows.append({
            "method": method,
            "composition_count": int(len(subset)),
            "style_score_count": int(len(scores)),
            "mean_style_score": (
                float(scores.mean())
                if len(scores) else None
            ),
            "median_style_score": (
                float(scores.median())
                if len(scores) else None
            ),
            "preservation_evaluated_count": int(
                len(preservation)
            ),
            "preservation_pass_count": int(
                (preservation == True).sum()
            ),
            "preservation_fail_count": int(
                (preservation == False).sum()
            ),
        })

    return pd.DataFrame(rows)


def build_paired_style_comparison(batch_table):
    pivot = batch_table.pivot(
        index=["composition_id", "target_genre"],
        columns="method",
        values="style_score",
    )

    pivot = pivot.reindex(columns=list(METHODS))

    rows = []

    comparisons = [
        ("B0", "B1"),
        ("B0", "M"),
        ("B1", "M"),
    ]

    for first, second in comparisons:
        paired = pivot[[first, second]].dropna()

        differences = (
            paired[second].astype(float)
            - paired[first].astype(float)
        )

        rows.append({
            "method_1": first,
            "method_2": second,
            "paired_compositions": int(len(paired)),
            "mean_score_difference": (
                float(differences.mean())
                if len(differences) else None
            ),
            "median_score_difference": (
                float(differences.median())
                if len(differences) else None
            ),
        })

    return pd.DataFrame(rows)


def create_batch_report(
    batch_table,
    method_summary,
    paired_comparison,
):
    lines = [
        "# CSC 575 Batch Evaluation",
        "",
        "## Evaluation Coverage",
        "",
        f"Total arrangement rows: {len(batch_table)}",
        "",
        "## Method Comparison",
        "",
        method_summary.to_markdown(index=False),
        "",
        "## Paired Style Comparison",
        "",
        paired_comparison.to_markdown(index=False),
        "",
        "## Limitations",
        "",
        "- Style scores are classifier confidence scores, "
        "not direct measures of musical quality.",
        "- Missing preservation checks are not "
        "counted as successful.",
        "- Chord and phrase checks require "
        "verified annotations.",
        "- This report provides descriptive "
        "comparisons, not statistical significance tests.",
        "",
    ]

    return "\n".join(lines)


def save_batch_results(
    batch_table,
    method_summary,
    paired_comparison,
    output_directory,
):
    output_directory = Path(output_directory)
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    batch_table.to_csv(
        output_directory / "batch_evaluation.csv",
        index=False,
    )

    method_summary.to_csv(
        output_directory / "method_comparison.csv",
        index=False,
    )

    paired_comparison.to_csv(
        output_directory / "paired_style_comparison.csv",
        index=False,
    )

    report = create_batch_report(
        batch_table,
        method_summary,
        paired_comparison,
    )

    (output_directory / "batch_report.md").write_text(
        report,
        encoding="utf-8",
    )

    print(f"Batch evaluation saved to: {output_directory}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "manifest",
        help="CSV listing evaluation files for each method.",
    )

    parser.add_argument(
        "--output",
        default="workstreams/vinay/results/batch_evaluation",
    )

    args = parser.parse_args()

    manifest, base_directory = load_batch_manifest(
        args.manifest
    )

    batch_table = build_batch_table(
        manifest,
        base_directory,
    )

    method_summary = summarize_methods(batch_table)

    paired_comparison = build_paired_style_comparison(
        batch_table
    )

    save_batch_results(
        batch_table,
        method_summary,
        paired_comparison,
        args.output,
    )


if __name__ == "__main__":
    main()
