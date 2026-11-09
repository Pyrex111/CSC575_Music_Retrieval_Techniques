
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


METHODS = ("B0", "B1", "M")
QUESTIONS = (
    "style_similarity",
    "musical_quality",
    "melody_preservation",
    "overall_preference",
)


def read_json(path):
    if path is None:
        return None

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    with path.open(encoding="utf-8") as file:
        return json.load(file)


def read_csv(path):
    if path is None:
        return None

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    return pd.read_csv(path)


def json_safe(value):
    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())

    if isinstance(value, np.generic):
        return json_safe(value.item())

    if isinstance(value, float) and not np.isfinite(value):
        return None

    if pd.isna(value):
        return None

    return value


def summarize_classifier(metrics):
    if metrics is None:
        return {
            "status": "not_available",
            "selected_model": None,
            "test_macro_f1": None,
        }

    return {
        "status": "available",
        "selected_model": metrics.get("selected_model"),
        "test_macro_f1": metrics.get("test_macro_f1"),
        "metrics": metrics,
    }


def summarize_ranking(ranking):
    if ranking is None:
        return {
            "status": "not_available",
            "candidate_count": 0,
        }

    if not isinstance(ranking, list):
        raise ValueError(
            "Ranking results must be a JSON list."
        )

    return {
        "status": "available",
        "candidate_count": len(ranking),
        "candidates": ranking,
    }


def summarize_preservation(preservation, chords):
    if preservation is None and chords is None:
        return {
            "status": "not_available",
            "overall_preserved": None,
        }

    checks = {}

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

        checks["phrases"] = (
            phrase.get("phrase_boundaries_preserved")
            if phrase.get("phrase_boundaries_checked")
            else None
        )

    if chords is not None:
        checks["chords"] = (
            chords.get("chords_preserved")
            if chords.get("chords_checked")
            else None
        )

    evaluated = [
        value for value in checks.values()
        if value is not None
    ]

    if not evaluated:
        overall = None
    elif not all(evaluated):
        overall = False
    elif all(
        value is not None
        for value in checks.values()
    ):
        overall = True
    else:
        overall = None

    return {
        "status": "available",
        "checks": checks,
        "overall_preserved": overall,
        "evaluated_check_count": len(evaluated),
        "missing_check_count": sum(
            value is None for value in checks.values()
        ),
    }


def summarize_listening(
    rating_summary,
    friedman_tests,
    pairwise_tests,
):
    if all(
        item is None
        for item in (
            rating_summary,
            friedman_tests,
            pairwise_tests,
        )
    ):
        return {"status": "not_available"}

    if rating_summary is None:
        raise ValueError(
            "Rating summary is required when "
            "listening analysis is supplied."
        )

    required = {
        "question",
        "method",
        "rating_count",
        "mean_rating",
        "median_rating",
        "ci_lower",
        "ci_upper",
    }

    if not required.issubset(rating_summary.columns):
        raise ValueError(
            "Rating summary is missing required columns."
        )

    invalid_methods = (
        set(rating_summary["method"].dropna()) - set(METHODS)
    )

    if invalid_methods:
        raise ValueError(
            f"Unknown listening methods: {invalid_methods}"
        )

    return {
        "status": "available",
        "rating_summary": json_safe(
            rating_summary.to_dict("records")
        ),
        "friedman_tests": (
            json_safe(friedman_tests.to_dict("records"))
            if friedman_tests is not None else None
        ),
        "pairwise_tests": (
            json_safe(pairwise_tests.to_dict("records"))
            if pairwise_tests is not None else None
        ),
    }


def build_evaluation_report(
    classifier_metrics=None,
    ranking_results=None,
    preservation_results=None,
    chord_results=None,
    rating_summary=None,
    friedman_tests=None,
    pairwise_tests=None,
):
    report = {
        "project": "CSC 575 Cross-Genre Song Transformer",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "methods": list(METHODS),
        "style_classifier": summarize_classifier(
            classifier_metrics
        ),
        "candidate_ranking": summarize_ranking(
            ranking_results
        ),
        "preservation": summarize_preservation(
            preservation_results,
            chord_results,
        ),
        "listening_study": summarize_listening(
            rating_summary,
            friedman_tests,
            pairwise_tests,
        ),
    }

    sections = [
        "style_classifier",
        "candidate_ranking",
        "preservation",
        "listening_study",
    ]

    available = [
        section
        for section in sections
        if report[section]["status"] == "available"
    ]

    missing = [
        section
        for section in sections
        if report[section]["status"] == "not_available"
    ]

    report["completion"] = {
        "available_sections": available,
        "missing_sections": missing,
        "available_count": len(available),
        "total_count": len(sections),
        "all_sections_available": len(missing) == 0,
    }

    report["limitations"] = [
        "Classifier performance must be evaluated "
        "on real labelled MIDI compositions.",
        "Candidate ranking scores measure learned "
        "style confidence, not musical quality.",
        "Phrase and chord preservation require "
        "verified annotations.",
        "Listening-study conclusions require "
        "genuine participant responses.",
        "Participant-level statistical tests do "
        "not explicitly model composition effects.",
    ]

    return json_safe(report)


def format_value(value):
    if value is None:
        return "Not available"

    if isinstance(value, bool):
        return "Yes" if value else "No"

    if isinstance(value, float):
        return f"{value:.4f}"

    return str(value)


def create_markdown_report(report):
    lines = [
        "# CSC 575 Cross-Genre Song Transformer",
        "",
        "## Evaluation Report",
        "",
        f"Generated: {report['generated_at_utc']}",
        "",
        "## 1. Evaluation Coverage",
        "",
        "| Component | Status |",
        "|---|---|",
    ]

    section_names = {
        "style_classifier": "Style classification",
        "candidate_ranking": "Candidate ranking",
        "preservation": "Preservation evaluation",
        "listening_study": "Listening study",
    }

    for key, name in section_names.items():
        status = report[key]["status"]

        lines.append(
            f"| {name} | {status.replace('_', ' ')} |"
        )

    classifier = report["style_classifier"]

    lines.extend([
        "",
        "## 2. Style Classification",
        "",
        "Selected model: "
        + format_value(classifier["selected_model"]),
        "",
        "Held-out macro-F1: "
        + format_value(classifier["test_macro_f1"]),
        "",
    ])

    ranking = report["candidate_ranking"]

    lines.extend([
        "## 3. Candidate Ranking",
        "",
        "Ranked candidates: "
        + str(ranking["candidate_count"]),
        "",
    ])

    preservation = report["preservation"]

    lines.extend([
        "## 4. Preservation Evaluation",
        "",
    ])

    if preservation["status"] == "available":
        lines.extend([
            "| Check | Result |",
            "|---|---|",
        ])

        for check, result in preservation["checks"].items():
            lines.append(
                f"| {check.title()} | {format_value(result)} |"
            )

        lines.extend([
            "",
            "Overall preservation: "
            + format_value(
                preservation["overall_preserved"]
            ),
            "",
        ])
    else:
        lines.extend([
            "Preservation results are not available.",
            "",
        ])

    listening = report["listening_study"]

    lines.extend([
        "## 5. Listening Evaluation",
        "",
    ])

    if listening["status"] == "available":
        lines.extend([
            "| Question | Method | N | Mean | Median | 95% CI |",
            "|---|---|---:|---:|---:|---:|",
        ])

        for row in listening["rating_summary"]:
            lines.append(
                "| {question} | {method} | {count} | "
                "{mean} | {median} | {ci} |".format(
                    question=row["question"],
                    method=row["method"],
                    count=format_value(row["rating_count"]),
                    mean=format_value(row["mean_rating"]),
                    median=format_value(row["median_rating"]),
                    ci=(
                        f'{format_value(row["ci_lower"])} to '
                        f'{format_value(row["ci_upper"])}'
                    ),
                )
            )

        lines.append("")
    else:
        lines.extend([
            "Listening results are not available.",
            "",
        ])

    lines.extend([
        "## 6. Limitations",
        "",
    ])

    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")

    lines.extend([
        "",
        "## 7. Completion",
        "",
        "Available sections: "
        + str(report["completion"]["available_count"])
        + " / "
        + str(report["completion"]["total_count"]),
        "",
        "Section availability does not imply that "
        "the evaluation has passed or that the "
        "results are statistically conclusive.",
        "",
    ])

    return "\n".join(lines)


def save_evaluation_report(report, output_directory):
    output_directory = Path(output_directory)

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = output_directory / "evaluation_report.json"
    markdown_path = output_directory / "evaluation_report.md"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, allow_nan=False)

    markdown_path.write_text(
        create_markdown_report(report),
        encoding="utf-8",
    )

    print(f"Evaluation report saved to: {output_directory}")

    return json_path, markdown_path


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--classifier-metrics")
    parser.add_argument("--ranking")
    parser.add_argument("--preservation")
    parser.add_argument("--chords")
    parser.add_argument("--rating-summary")
    parser.add_argument("--friedman-tests")
    parser.add_argument("--pairwise-tests")

    parser.add_argument(
        "--output",
        default="workstreams/vinay/results/final_evaluation",
    )

    args = parser.parse_args()

    report = build_evaluation_report(
        classifier_metrics=read_json(
            args.classifier_metrics
        ),
        ranking_results=read_json(args.ranking),
        preservation_results=read_json(
            args.preservation
        ),
        chord_results=read_json(args.chords),
        rating_summary=read_csv(args.rating_summary),
        friedman_tests=read_csv(args.friedman_tests),
        pairwise_tests=read_csv(args.pairwise_tests),
    )

    save_evaluation_report(report, args.output)


if __name__ == "__main__":
    main()
