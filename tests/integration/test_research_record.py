"""Integrity of the committed Phase 4 research record (scripts/verify_research.py).

Runs the fast provenance checks against the real committed files, and checks that
the verifier detects tampering on a copy. The full re-analysis (``--reanalyse``)
takes minutes and runs as its own CI step.
"""

from __future__ import annotations

import json
import runpy
import shutil
from pathlib import Path
from typing import Any

import pytest

from know_your_fan.research import experiments, reporting

ROOT = experiments.REPO_ROOT
_verify: dict[str, Any] = runpy.run_path(str(ROOT / "scripts" / "verify_research.py"))
verify_main = _verify["main"]


def _research_copy(tmp_path: Path) -> Path:
    for part in ("experiments", "docs/research"):
        shutil.copytree(
            ROOT / part,
            tmp_path / part,
            ignore=shutil.ignore_patterns(
                "observations.csv", "summary.json", "observation_metrics.csv", "trial_scores.*"
            ),
        )
    return tmp_path


def test_committed_research_record_verifies(capsys: pytest.CaptureFixture[str]) -> None:
    assert verify_main([]) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out
    assert "E1+E2+E3 total 19,200 OCR runs" in out


def test_verifier_detects_an_edited_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _research_copy(tmp_path)
    config = root / "experiments" / "configs" / "e3_test.toml"
    config.write_text(config.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    assert verify_main(["--root", str(root)]) == 1
    assert "FAIL e3_test: config hash matches" in capsys.readouterr().out


def test_verifier_detects_a_changed_frozen_selection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _research_copy(tmp_path)
    path = root / reporting.SELECTION
    selection = json.loads(path.read_text(encoding="utf-8"))
    selection["e3_strategies"] = ["P0_baseline", "P2_gray"]
    path.write_text(json.dumps(selection), encoding="utf-8")
    assert verify_main(["--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "FAIL E3 strategies are the frozen ones" in out
    assert "FAIL app-facing files carry the frozen selection" in out


def test_app_summary_key_order_does_not_depend_on_hashing() -> None:
    pooled = {
        "cer": {},
        "wer": {},
        "name_token_recall": {},
        "latency_ms": {"preprocess_plus_ocr": {"median": 1.0}},
        "n_observations": 1,
        "n_sources": 1,
    }
    matching = {m: dict.fromkeys(("far", "frr", "tp", "fp", "tn", "fn", "tau"), 0) for m in
                reporting.MATCHER_LABELS}  # fmt: skip
    e3 = {
        "ocr": {"test/P0_baseline": {"pooled": pooled}, "test/P1_none": {"pooled": pooled}},
        "matching": {"test/P0_baseline": {"pooled": matching}},
    }
    summary = reporting._app_summary({"e3_test": e3}, {"preprocessing": "P1_none"})
    # Selected strategy first, then the baseline: the order of the committed file.
    assert list(summary["test_ocr"]) == ["test/P1_none", "test/P0_baseline"]
    same = reporting._app_summary({"e3_test": e3}, {"preprocessing": "P0_baseline"})
    assert list(same["test_ocr"]) == ["test/P0_baseline"]
