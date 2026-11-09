
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pretty_midi

from style_features import extract_style_features
from style_classifier import (
    FEATURE_NAMES,
    load_dataset,
    build_feature_table,
    train_and_select_model,
    save_results,
)
from style_analysis import (
    check_feature_columns,
    analyze_errors,
    analyze_feature_importance,
    analyze_feature_groups,
    save_analysis,
)
from style_ranking import (
    calculate_style_score,
    rank_candidates,
    save_ranking,
)
from preservation_evaluation import (
    evaluate_preservation,
    save_preservation_results,
)


# PI1: Style feature extraction

def create_test_midi():
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)

    melody = pretty_midi.Instrument(program=0)
    melody.notes.append(pretty_midi.Note(100, 72, 0.0, 1.0))
    melody.notes.append(pretty_midi.Note(100, 74, 1.0, 2.0))
    midi.instruments.append(melody)

    bass = pretty_midi.Instrument(program=32)
    bass.notes.append(pretty_midi.Note(100, 48, 0.0, 0.5))
    bass.notes.append(pretty_midi.Note(100, 52, 0.5, 1.0))
    bass.notes.append(pretty_midi.Note(100, 55, 1.0, 1.5))
    bass.notes.append(pretty_midi.Note(100, 48, 1.5, 2.0))
    midi.instruments.append(bass)

    piano = pretty_midi.Instrument(program=0)
    piano.notes.append(pretty_midi.Note(100, 60, 0.0, 1.0))
    piano.notes.append(pretty_midi.Note(100, 64, 0.0, 1.0))
    piano.notes.append(pretty_midi.Note(100, 67, 0.0, 1.0))
    midi.instruments.append(piano)

    return midi


def test_basic_features():
    features = extract_style_features(create_test_midi(), 0)

    assert len(features) == 21
    assert np.isclose(features["note_density"], 1.75)
    assert np.isclose(features["average_note_duration"], 5 / 7)
    assert np.isclose(features["average_polyphony"], 2.5)
    assert np.isclose(features["offbeat_activity"], 0.0)
    assert np.isclose(features["average_bass_interval"], 14 / 3)
    assert np.isclose(features["onset_position_0"], 1.0)
    assert np.isclose(features["pitch_class_0"], 3 / 7)
    assert np.isclose(features["pitch_class_4"], 2 / 7)
    assert np.isclose(features["pitch_class_7"], 2 / 7)

    print("Basic feature test passed")


def test_offbeat_notes():
    midi = create_test_midi()
    midi.instruments[2].notes.append(
        pretty_midi.Note(100, 69, 0.25, 0.5)
    )

    features = extract_style_features(midi, 0)

    assert np.isclose(features["offbeat_activity"], 1 / 8)
    assert np.isclose(features["onset_position_2"], 1 / 8)

    print("Offbeat activity test passed")


def test_overlapping_notes():
    midi = create_test_midi()
    midi.instruments[2].notes.append(
        pretty_midi.Note(100, 72, 0.5, 1.5)
    )

    features = extract_style_features(midi, 0)

    assert np.isclose(features["average_polyphony"], 3.0)

    print("Overlapping notes test passed")


def test_empty_accompaniment():
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)

    melody = pretty_midi.Instrument(program=0)
    melody.notes.append(pretty_midi.Note(100, 72, 0.0, 1.0))
    midi.instruments.append(melody)

    features = extract_style_features(midi, 0)

    assert len(features) == 21
    assert all(np.isclose(value, 0) for value in features.values())

    print("Empty accompaniment test passed")


def test_melody_exclusion():
    midi = create_test_midi()
    original = extract_style_features(midi, 0)

    midi.instruments[0].notes[0].pitch = 85
    midi.instruments[0].notes[1].pitch = 90

    updated = extract_style_features(midi, 0)

    for feature in original:
        assert np.isclose(original[feature], updated[feature])

    print("Melody exclusion test passed")


# PI2/PI3: Classification

def create_test_features():
    rows = []
    random = np.random.default_rng(42)

    for split, count in [
        ("train", 20),
        ("validation", 8),
        ("test", 8),
    ]:
        for i in range(count):
            genre = "jazz" if i % 2 == 0 else "rock"

            row = {
                "midi_path": f"{split}_{i}.mid",
                "composition_id": f"{split}_{i}",
                "genre": genre,
                "split": split,
            }

            for feature in FEATURE_NAMES:
                row[feature] = random.normal(0, 0.1)

            if genre == "jazz":
                row["offbeat_activity"] = (
                    0.8 + random.normal(0, 0.05)
                )
                row["note_density"] = (
                    3.0 + random.normal(0, 0.1)
                )
            else:
                row["offbeat_activity"] = (
                    0.2 + random.normal(0, 0.05)
                )
                row["note_density"] = (
                    1.5 + random.normal(0, 0.1)
                )

            rows.append(row)

    return pd.DataFrame(rows)


def test_dataset_loading():
    with tempfile.TemporaryDirectory() as folder:
        csv_path = Path(folder) / "dataset.csv"

        data = pd.DataFrame([
            {
                "midi_path": "a.mid",
                "composition_id": "A",
                "genre": "jazz",
                "split": "train",
            },
            {
                "midi_path": "b.mid",
                "composition_id": "B",
                "genre": "rock",
                "split": "validation",
            },
            {
                "midi_path": "c.mid",
                "composition_id": "C",
                "genre": "jazz",
                "split": "test",
            },
        ])

        data.to_csv(csv_path, index=False)

        assert len(load_dataset(csv_path)) == 3

        print("Dataset loading test passed")


def test_composition_leakage():
    with tempfile.TemporaryDirectory() as folder:
        csv_path = Path(folder) / "dataset.csv"

        data = pd.DataFrame([
            {
                "midi_path": "a.mid",
                "composition_id": "A",
                "genre": "jazz",
                "split": "train",
            },
            {
                "midi_path": "b.mid",
                "composition_id": "A",
                "genre": "jazz",
                "split": "test",
            },
            {
                "midi_path": "c.mid",
                "composition_id": "B",
                "genre": "rock",
                "split": "validation",
            },
        ])

        data.to_csv(csv_path, index=False)

        try:
            load_dataset(csv_path)
            raise AssertionError("Composition leakage was not detected")
        except ValueError as error:
            assert "multiple splits" in str(error)

        print("Composition leakage test passed")


def test_midi_feature_table():
    with tempfile.TemporaryDirectory() as folder:
        dataset_directory = Path(folder)
        rows = []

        examples = [
            ("train", "jazz", "composition_1"),
            ("train", "rock", "composition_2"),
            ("validation", "jazz", "composition_3"),
            ("validation", "rock", "composition_4"),
            ("test", "jazz", "composition_5"),
            ("test", "rock", "composition_6"),
        ]

        for i, (split, genre, composition_id) in enumerate(examples):
            midi = create_test_midi()
            midi_path = dataset_directory / f"example_{i}.mid"
            midi.write(str(midi_path))

            rows.append({
                "midi_path": midi_path.name,
                "composition_id": composition_id,
                "genre": genre,
                "split": split,
                "melody_track_index": 0,
            })

        csv_path = dataset_directory / "dataset.csv"
        pd.DataFrame(rows).to_csv(csv_path, index=False)

        data = load_dataset(csv_path)
        feature_table = build_feature_table(
            data, dataset_directory
        )

        assert len(feature_table) == 6
        assert all(
            feature in feature_table.columns
            for feature in FEATURE_NAMES
        )
        assert feature_table[FEATURE_NAMES].notna().all().all()
        assert np.isfinite(
            feature_table[FEATURE_NAMES].to_numpy(dtype=float)
        ).all()
        assert feature_table["composition_id"].tolist() == [
            example[2] for example in examples
        ]
        assert feature_table["genre"].tolist() == [
            example[1] for example in examples
        ]
        assert feature_table["split"].tolist() == [
            example[0] for example in examples
        ]
        assert np.isclose(
            feature_table.iloc[0]["note_density"], 1.75
        )

        print("MIDI feature table integration test passed")


def test_classifier_training():
    features = create_test_features()
    model, metrics, predictions = train_and_select_model(features)

    assert metrics["selected_model"] in [
        "logistic_regression", "random_forest"
    ]
    assert 0 <= metrics["test_macro_f1"] <= 1
    assert len(predictions) == 8
    assert set(model.classes_) == {"jazz", "rock"}

    print("Classifier training test passed")

    return model, metrics, predictions


def test_result_saving(model, metrics, predictions):
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder)
        save_results(model, metrics, predictions, output)

        assert (output / "style_classifier.joblib").exists()
        assert (output / "metrics.json").exists()
        assert (output / "test_predictions.csv").exists()

        print("Result saving test passed")


# PI4: Analysis

def test_feature_validation():
    data = create_test_features()
    check_feature_columns(data)

    assert len(FEATURE_NAMES) == 21
    assert not any(
        "program" in name or "instrument" in name
        for name in FEATURE_NAMES
    )

    print("Feature validation test passed")


def test_error_analysis(model):
    errors = analyze_errors(create_test_features(), model)

    assert isinstance(errors, pd.DataFrame)
    assert set(errors.columns) == {
        "midi_path",
        "composition_id",
        "genre",
        "predicted_genre",
    }
    assert len(errors) <= 8

    print("Error analysis test passed")

    return errors


def test_feature_importance(model):
    importance = analyze_feature_importance(
        create_test_features(), model
    )

    assert len(importance) == 21
    assert set(importance["feature"]) == set(FEATURE_NAMES)
    assert np.isfinite(importance["importance_mean"]).all()
    assert np.isfinite(importance["importance_std"]).all()

    print("Feature importance test passed")

    return importance


def test_feature_group_ablation(model):
    groups = analyze_feature_groups(
        create_test_features(), model
    )

    assert len(groups) == 4
    assert set(groups["excluded_group"]) == {
        "rhythm",
        "duration_polyphony",
        "bass",
        "pitch_class",
    }
    assert groups["reduced_macro_f1"].between(0, 1).all()

    print("Feature group ablation test passed")

    return groups


def test_analysis_saving(errors, importance, groups):
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder)
        save_analysis(errors, importance, groups, output)

        assert (output / "classification_errors.csv").exists()
        assert (output / "feature_importance.csv").exists()
        assert (output / "feature_group_ablation.csv").exists()
        assert (output / "analysis_summary.json").exists()

        print("Analysis saving test passed")


# PI5: Candidate ranking

def test_style_score(model):
    features = create_test_features().iloc[0].to_dict()
    score = calculate_style_score(model, features, "jazz")

    assert 0 <= score <= 1

    print("Style score test passed")


def test_invalid_target_genre(model):
    features = create_test_features().iloc[0].to_dict()

    try:
        calculate_style_score(model, features, "classical")
    except ValueError:
        print("Invalid target genre test passed")
        return

    raise AssertionError("Invalid target genre was accepted")


def test_candidate_ranking(model):
    with tempfile.TemporaryDirectory() as folder:
        candidates = []

        for i in range(3):
            midi = create_test_midi()
            midi_path = Path(folder) / f"candidate_{i}.mid"
            midi.write(str(midi_path))

            candidates.append({
                "candidate_id": f"candidate_{i}",
                "midi_path": str(midi_path),
                "melody_track_index": 0,
            })

        results = rank_candidates(model, candidates, "jazz")

        assert len(results) == 3
        assert [item["rank"] for item in results] == [1, 2, 3]
        assert all(
            results[i]["style_score"] >= results[i + 1]["style_score"]
            for i in range(len(results) - 1)
        )

        print("Candidate ranking test passed")


def test_ranking_saving():
    results = [{
        "candidate_id": "candidate_1",
        "midi_path": "candidate_1.mid",
        "target_genre": "jazz",
        "style_score": 0.8,
        "rank": 1,
    }]

    with tempfile.TemporaryDirectory() as folder:
        output_path = Path(folder) / "ranking.json"
        save_ranking(results, output_path)

        assert output_path.exists()

        with open(output_path) as file:
            assert json.load(file) == results

        print("Ranking saving test passed")


# Objective 2: Preservation evaluation

def test_identical_midi_preservation():
    original = create_test_midi()
    transformed = create_test_midi()

    results = evaluate_preservation(original, transformed)

    assert results["melody"]["melody_preserved"]
    assert results["tempo"]["tempo_preserved"]
    assert results["bars"]["bar_count_preserved"]
    assert not results["phrases"]["phrase_boundaries_checked"]
    assert results["overall_preserved"]

    print("Identical MIDI preservation test passed")


def test_changed_melody_pitch():
    original = create_test_midi()
    transformed = create_test_midi()

    transformed.instruments[0].notes[0].pitch = 80

    results = evaluate_preservation(original, transformed)

    assert not results["melody"]["same_pitches"]
    assert not results["melody"]["melody_preserved"]
    assert not results["overall_preserved"]

    print("Changed melody pitch test passed")


def test_changed_melody_onset():
    original = create_test_midi()
    transformed = create_test_midi()

    transformed.instruments[0].notes[1].start = 1.2

    results = evaluate_preservation(original, transformed)

    assert not results["melody"]["same_onsets"]
    assert not results["melody"]["melody_preserved"]
    assert not results["overall_preserved"]

    print("Changed melody onset test passed")


def test_changed_melody_duration():
    original = create_test_midi()
    transformed = create_test_midi()

    transformed.instruments[0].notes[0].end = 0.7

    results = evaluate_preservation(original, transformed)

    assert not results["melody"]["same_durations"]
    assert not results["melody"]["melody_preserved"]
    assert not results["overall_preserved"]

    print("Changed melody duration test passed")


def test_changed_tempo():
    original = create_test_midi()
    transformed = create_test_midi()

    transformed._tick_scales[0] = (
        0, 60.0 / (140 * transformed.resolution)
    )

    results = evaluate_preservation(original, transformed)

    assert not results["tempo"]["tempo_preserved"]
    assert not results["overall_preserved"]

    print("Changed tempo test passed")


def test_changed_bar_count():
    original = create_test_midi()
    transformed = create_test_midi()

    transformed.instruments[1].notes.append(
        pretty_midi.Note(100, 48, 4.0, 5.0)
    )

    results = evaluate_preservation(original, transformed)

    assert results["bars"]["original_bars"] == 1
    assert results["bars"]["transformed_bars"] == 3
    assert not results["bars"]["bar_count_preserved"]
    assert not results["overall_preserved"]

    print("Changed bar count test passed")


def test_phrase_boundaries():
    original = create_test_midi()
    transformed = create_test_midi()

    matching = evaluate_preservation(
        original,
        transformed,
        original_phrase_boundaries=[0.0, 1.0, 2.0],
        transformed_phrase_boundaries=[0.0, 1.0, 2.0],
    )

    assert matching["phrases"]["phrase_boundaries_checked"]
    assert matching["phrases"]["phrase_boundaries_preserved"]
    assert matching["overall_preserved"]

    mismatching = evaluate_preservation(
        original,
        transformed,
        original_phrase_boundaries=[0.0, 1.0, 2.0],
        transformed_phrase_boundaries=[0.0, 1.3, 2.0],
    )

    assert not mismatching["phrases"]["phrase_boundaries_preserved"]
    assert not mismatching["overall_preserved"]

    print("Phrase boundary test passed")


def test_preservation_saving():
    results = evaluate_preservation(
        create_test_midi(),
        create_test_midi(),
    )

    with tempfile.TemporaryDirectory() as folder:
        output_path = Path(folder) / "preservation.json"

        save_preservation_results(results, output_path)

        assert output_path.exists()

        with open(output_path) as file:
            saved_results = json.load(file)

        assert saved_results == results

        print("Preservation saving test passed")


# Objective 2: Listening study and end-to-end evaluation tests

def create_listening_manifest():
    rows = []

    for composition in ("song_a", "song_b"):
        for method in ("B0", "B1", "M"):
            rows.append({
                "composition_id": composition,
                "target_genre": "jazz",
                "method": method,
                "audio_path": f"{composition}_{method}.wav",
                "source_audio_path": f"{composition}_source.wav",
            })

    return pd.DataFrame(rows)


def create_synthetic_study():
    from listening_evaluation import create_listening_trials

    return create_listening_trials(
        create_listening_manifest(),
        participant_count=12,
        seed=42,
    )


def test_listening_protocol():
    from listening_evaluation import (
        create_listening_trials,
        validate_trial_balance,
        create_questionnaire,
    )

    manifest = create_listening_manifest()
    public, key, responses = create_synthetic_study()

    assert len(public) == len(key) == len(responses) == 72
    assert public["participant_id"].nunique() == 12
    assert not {"method", "composition_id"}.intersection(public.columns)
    assert set(key["method"]) == {"B0", "B1", "M"}
    assert not public.duplicated(
        ["participant_id", "trial_id"]
    ).any()

    balance = validate_trial_balance(public, key)

    assert not balance.empty
    assert balance["count"].nunique() == 1

    second = create_listening_trials(
        manifest,
        participant_count=12,
        seed=42,
    )

    for first_frame, second_frame in zip(
        (public, key, responses),
        second,
    ):
        pd.testing.assert_frame_equal(
            first_frame, second_frame
        )

    assert "style_fit" in str(create_questionnaire())

    print(
        "Listening protocol, anonymity, balance "
        "and reproducibility tests passed"
    )


def test_listening_manifest_validation():
    from listening_evaluation import load_manifest

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "manifest.csv"
        data = create_listening_manifest()

        data.to_csv(path, index=False)

        assert len(load_manifest(path)) == 6

        invalid = data[data["method"] != "M"]
        invalid.to_csv(path, index=False)

        try:
            load_manifest(path)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Incomplete B0/B1/M group was accepted"
            )

    print("Listening manifest validation test passed")


def write_synthetic_responses(folder, missing=False):
    public, key, responses = create_synthetic_study()

    values = {"B0": 2, "B1": 3, "M": 5}

    responses = responses.merge(
        key[["participant_id", "trial_id", "method"]],
        on=["participant_id", "trial_id"],
        validate="one_to_one",
    )

    for question in (
        "style_fit",
        "source_recognizability",
        "musical_coherence",
    ):
        responses[question] = (
            responses["method"].map(values).astype(float)
        )

    responses = responses.drop(columns="method")

    if missing:
        responses.loc[0, "style_fit"] = np.nan

    responses_path = Path(folder) / "responses.csv"
    key_path = Path(folder) / "private_key.csv"

    responses.to_csv(responses_path, index=False)
    key.to_csv(key_path, index=False)

    return responses_path, key_path


def test_response_validation():
    from listening_analysis import load_study_data

    with tempfile.TemporaryDirectory() as folder:
        response_path, key_path = write_synthetic_responses(
            folder
        )

        ratings, key = load_study_data(
            response_path,
            key_path,
        )

        assert len(ratings) == len(key) == 72

        responses = pd.read_csv(response_path)
        responses.loc[0, "style_fit"] = 6
        responses.to_csv(response_path, index=False)

        try:
            load_study_data(response_path, key_path)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Out-of-range rating was accepted"
            )

        responses.loc[0, "style_fit"] = 3

        responses = pd.concat(
            [responses, responses.iloc[[0]]],
            ignore_index=True,
        )

        responses.to_csv(response_path, index=False)

        try:
            load_study_data(response_path, key_path)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Duplicate response was accepted"
            )

    print("Listening response validation test passed")


def test_listening_analysis_pipeline():
    from listening_analysis import analyze_listening_study
    from evaluation_report import (
        build_evaluation_report,
        create_markdown_report,
        save_evaluation_report,
    )

    with tempfile.TemporaryDirectory() as folder:
        response_path, key_path = write_synthetic_responses(
            folder,
            missing=True,
        )

        output = Path(folder) / "analysis"

        summary, pairs, coverage = analyze_listening_study(
            response_path,
            key_path,
            output,
            bootstrap_iterations=40,
            seed=42,
        )

        assert len(summary) == 9
        assert len(pairs) == 9
        assert summary["rating_count"].min() == 23
        assert summary["rating_count"].max() == 24
        assert (
            summary["mean_rating"].dropna().between(1, 5)
        ).all()

        comparison = pairs[
            (pairs["question"] == "musical_coherence")
            & (pairs["method_1"] == "B0")
            & (pairs["method_2"] == "M")
        ]

        assert len(comparison) == 1
        assert abs(
            comparison.iloc[0]["mean_difference"] - 3
        ) < 1e-9

        assert (
            output / "participant_coverage.csv"
        ).exists()

        assert (
            output / "analysis_metadata.json"
        ).exists()

        assert not coverage.empty

        report = build_evaluation_report(
            rating_summary=summary,
            pairwise_tests=pairs,
        )

        markdown = create_markdown_report(report)

        assert "Listening Evaluation" in markdown
        assert "style_fit" in markdown

        report_dir = Path(folder) / "report"

        save_evaluation_report(
            report,
            report_dir,
        )

        assert (
            report_dir / "evaluation_report.json"
        ).exists()

        assert (
            report_dir / "evaluation_report.md"
        ).exists()

    print(
        "Listening statistics and final report "
        "integration test passed"
    )


def test_chord_evaluation():
    from chord_evaluation import compare_chords

    chords = [
        {
            "start": 0.0,
            "end": 2.0,
            "label": "Cmaj",
        }
    ]

    assert compare_chords(
        chords,
        chords,
    )["chords_preserved"] is True

    changed = [
        {
            "start": 0.0,
            "end": 2.0,
            "label": "Gmaj",
        }
    ]

    assert compare_chords(
        chords,
        changed,
    )["chords_preserved"] is False

    assert compare_chords()["chords_checked"] is False

    print("Chord evaluation test passed")


def test_batch_comparison():
    from batch_evaluation import (
        load_batch_manifest,
        build_batch_table,
        summarize_methods,
        build_paired_style_comparison,
        save_batch_results,
    )

    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        manifest_path = folder / "batch.csv"

        rows = []

        for composition in ("song_a", "song_b"):
            for method in ("B0", "B1", "M"):
                rows.append({
                    "composition_id": composition,
                    "target_genre": "jazz",
                    "method": method,
                })

        pd.DataFrame(rows).to_csv(
            manifest_path,
            index=False,
        )

        manifest, base = load_batch_manifest(
            manifest_path
        )

        table = build_batch_table(
            manifest,
            base,
        )

        assert len(table) == 6
        assert table["overall_preserved"].isna().all()

        summary = summarize_methods(table)
        paired = build_paired_style_comparison(table)

        assert len(summary) == 3
        assert len(paired) == 3
        assert (
            paired["paired_compositions"] == 0
        ).all()

        output = folder / "batch_results"

        save_batch_results(
            table,
            summary,
            paired,
            output,
        )

        assert (output / "batch_report.md").exists()
        assert (
            output / "paired_style_comparison.csv"
        ).exists()

    print(
        "Batch comparison and missing-data "
        "handling test passed"
    )


# Run all tests

if __name__ == "__main__":
    print("\n--- PI1: Feature Extraction ---")
    test_basic_features()
    test_offbeat_notes()
    test_overlapping_notes()
    test_empty_accompaniment()
    test_melody_exclusion()

    print("\n--- PI2/PI3: Classification ---")
    test_dataset_loading()
    test_composition_leakage()
    test_midi_feature_table()

    model, metrics, predictions = test_classifier_training()
    test_result_saving(model, metrics, predictions)

    print("\n--- PI4: Analysis ---")
    test_feature_validation()
    errors = test_error_analysis(model)
    importance = test_feature_importance(model)
    groups = test_feature_group_ablation(model)
    test_analysis_saving(errors, importance, groups)

    print("\n--- PI5: Candidate Ranking ---")
    test_style_score(model)
    test_invalid_target_genre(model)
    test_candidate_ranking(model)
    test_ranking_saving()

    print("\n--- Objective 2: Preservation Evaluation ---")
    test_identical_midi_preservation()
    test_changed_melody_pitch()
    test_changed_melody_onset()
    test_changed_melody_duration()
    test_changed_tempo()
    test_changed_bar_count()
    test_phrase_boundaries()
    test_preservation_saving()

    print("\n--- Objective 2: Listening, Statistics and Reporting ---")
    test_listening_protocol()
    test_listening_manifest_validation()
    test_response_validation()
    test_listening_analysis_pipeline()
    test_chord_evaluation()
    test_batch_comparison()

    print("\nAll 33 synthetic tests passed!")
