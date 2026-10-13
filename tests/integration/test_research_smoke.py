"""Research smoke test with the real Tesseract engine (small, bounded, deterministic inputs).

Runs the full CLI pipeline (run, evaluate, report) on 2 sources x 2 conditions x 2
strategies in a temporary directory. In CI ``KYF_REQUIRE_OCR=1`` turns a missing
engine into a failure; the full benchmark is never run here.
"""

from __future__ import annotations

import json
import os
import runpy
import shutil
from pathlib import Path

import pytest

from know_your_fan.research import experiments

REQUIRED = os.environ.get("KYF_REQUIRE_OCR") == "1"
if shutil.which("tesseract") is None:
    if REQUIRED:
        pytest.fail("KYF_REQUIRE_OCR=1 but Tesseract is not on PATH", pytrace=False)
    pytest.skip("Tesseract OCR is not installed", allow_module_level=True)

pytestmark = pytest.mark.ocr

SMOKE = """
experiment_id = "smoke"
description = "CI smoke test"
splits = ["dev"]
conditions = ["clean", "blur_1"]
strategies = ["P0_baseline", "P5_upscale2"]
max_sources_per_split = 2
[dataset]
seed = 20261013
sources_per_split = { dev = 80, val = 80, test = 160 }
[execution]
workers = 2
ocr_timeout_seconds = 15
"""


def test_research_pipeline_with_real_engine(tmp_path: Path) -> None:
    config = tmp_path / "smoke.toml"
    config.write_text(SMOKE, encoding="utf-8")
    main = runpy.run_path(str(experiments.REPO_ROOT / "scripts" / "run_research.py"))["main"]
    root = ["--root", str(tmp_path)]
    assert main(["run", "--config", str(config), "--environment", "smoke", *root]) == 0
    assert main(["evaluate", "--config", str(config), *root]) == 0
    assert main(["report", *root]) == 0

    out = experiments.results_dir(tmp_path, "smoke")
    rows = experiments.read_observations(out / "observations.csv")
    assert len(rows) == 8
    assert {r["status"] for r in rows} == {"ok"}
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    env = meta["runs"][0]["environment"]
    assert env["tesseract_version"] != "unavailable"
    assert {"eng", "por"} <= set(env["tesseract_languages"])
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    clean = summary["ocr"]["dev/P0_baseline"]["by_condition"]["clean"]
    # Sanity bound only (not an accuracy claim): clean synthetic cards read almost perfectly.
    assert clean["cer"]["estimate"] < 0.05
    assert summary["matching"]["dev/P0_baseline"]["pooled"]["M0_baseline"]["tp"] >= 1
