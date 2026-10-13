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


# ------------------------------------------------------------------ Phase 5: explorer data

REPO = presentation.REPO_ROOT


def test_committed_explorer_agrees_with_the_frozen_phase4_summary() -> None:
    """Integrity: the interactive data must equal the committed Phase 4 numbers."""
    explorer = presentation.load_explorer(REPO)
    summary = presentation.load_results(REPO).summary
    assert explorer is not None
    assert summary is not None
    for key, entry in summary["test_ocr"].items():
        strategy = key.split("/")[1]
        for metric in ("cer", "wer", "name_token_recall"):
            assert explorer["test_ocr"][strategy]["pooled"][metric] == entry[metric]
    for matcher, entry in summary["test_matching_P0"].items():
        for field in ("far", "frr", "tp", "fp", "tn", "fn", "tau"):
            assert explorer["test_matching"]["P0_baseline"][matcher][field] == entry[field]
    assert explorer["selection"] == {"preprocessing": "P1_none", "m2_tau": 0.05}


def test_committed_explorer_has_no_local_paths_or_usernames() -> None:
    raw = (REPO / presentation.EXPLORER_PATH).read_text(encoding="utf-8")
    for marker in (":\\\\", "Users", "/home/", "AppData", str(Path.home().name)):
        assert marker not in raw, marker


def test_explorer_helpers_shape_the_data() -> None:
    explorer = presentation.load_explorer(REPO)
    assert explorer is not None
    assert presentation.total_ocr_runs(explorer) == 2560 + 11520 + 5120
    rows = presentation.condition_rows(explorer, "cer")
    assert len(rows) == 16 * 2
    blur = presentation.condition_rows(explorer, "wer", "blur")
    assert {r["condition"] for r in blur} == {"blur_1", "blur_2", "blur_3"}
    assert all(r["ci_low"] <= r["estimate"] <= r["ci_high"] for r in rows)
    assert all(r["n_cards"] == 160 for r in rows)
    pre = presentation.preprocessing_rows(explorer, "cer")
    assert {(r["split"], r["n_cards"]) for r in pre} == {("dev", 80), ("val", 80)}
    assert len(pre) == 16
    sweep = presentation.sweep_rows(explorer)
    assert {r["split"] for r in sweep} == {"dev", "test"}
    taus = [r["tau"] for r in sweep if r["split"] == "test"]
    assert taus == sorted(taus)


def test_malformed_explorer_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / presentation.EXPLORER_PATH
    path.parent.mkdir(parents=True)
    for content in ("not json", "[]", json.dumps({"runs": {}})):
        path.write_text(content, encoding="utf-8")
        assert presentation.load_explorer(tmp_path) is None
    assert presentation.load_explorer(tmp_path / "missing") is None
