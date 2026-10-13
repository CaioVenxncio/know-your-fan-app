from __future__ import annotations

import json
from pathlib import Path

from know_your_fan.research import presentation


def test_missing_files_give_unavailable_results(tmp_path: Path) -> None:
    results = presentation.load_results(tmp_path)
    assert not results.available
    assert not results.is_final
    assert results.figures == []


def test_corrupt_summary_is_treated_as_unavailable(tmp_path: Path) -> None:
    path = tmp_path / presentation.SUMMARY_PATH
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert not presentation.load_results(tmp_path).available
    path.write_text("[1, 2, 3]", encoding="utf-8")  # valid JSON, wrong shape
    assert not presentation.load_results(tmp_path).available


def test_rows_format_intervals_and_missing_values() -> None:
    summary = {
        "status": "final",
        "test_ocr": {
            "test/P5_upscale2": {
                "cer": {"estimate": 0.1234, "ci_low": 0.1, "ci_high": 0.15},
                "wer": {"estimate": None},
                "name_token_recall": {"estimate": 0.9, "ci_low": None, "ci_high": None},
                "median_latency_ms": 640.4,
                "n_observations": 10,
                "n_sources": 5,
            }
        },
        "test_matching_P0": {
            "M2_tolerant": {
                "far": {"estimate": 0.01, "ci_low": 0.0, "ci_high": 0.02},
                "frr": {"estimate": 0.3, "ci_low": 0.25, "ci_high": 0.35},
                "tp": 7, "fp": 1, "tn": 20, "fn": 3, "tau": 0.05,
            }
        },
    }  # fmt: skip
    (ocr_row,) = presentation.ocr_rows(summary)
    assert ocr_row["Preprocessing"] == "P5_upscale2"
    assert ocr_row["CER [95% CI]"] == "0.123 [0.100, 0.150]"
    assert ocr_row["WER [95% CI]"] == "n/a"
    assert ocr_row["Name-token recall [95% CI]"] == "0.900"
    assert ocr_row["Median latency (ms)"] == "640"
    (match_row,) = presentation.matching_rows(summary)
    assert match_row["Matcher"] == "M2_tolerant (τ=0.05)"
    assert match_row["TP / FP / TN / FN"] == "7 / 1 / 20 / 3"


def test_existing_figures_are_listed_in_order(tmp_path: Path) -> None:
    directory = tmp_path / presentation.FIGURES_DIR
    directory.mkdir(parents=True)
    for name, _ in presentation.FIGURES[::-1]:
        (directory / name).write_bytes(b"png")
    (tmp_path / presentation.SUMMARY_PATH).parent.mkdir(parents=True)
    (tmp_path / presentation.SUMMARY_PATH).write_text(json.dumps({"status": "x"}), "utf-8")
    results = presentation.load_results(tmp_path)
    assert [p.name for p, _ in results.figures] == [n for n, _ in presentation.FIGURES]
