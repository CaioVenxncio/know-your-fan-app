"""Experiment configuration, runner, evaluation, reporting, and CLI (OCR engine replaced)."""

from __future__ import annotations

import csv
import json
import runpy
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from know_your_fan import ocr
from know_your_fan.research import evaluation, experiments, reporting
from know_your_fan.research.dataset import DatasetSpec, build_dataset

BASE_CONFIG: dict[str, Any] = {
    "experiment_id": "unit_test",
    "splits": ["dev"],
    "conditions": ["clean", "blur_1"],
    "strategies": ["P0_baseline", "P2_gray"],
    "max_sources_per_split": 3,
    "dataset": {"seed": 7, "sources_per_split": {"dev": 10, "val": 10, "test": 10}},
    "execution": {"workers": 1, "ocr_timeout_seconds": 5},
}
TOML = """
experiment_id = "unit_test"
splits = ["dev"]
conditions = ["clean", "blur_1"]
strategies = ["P0_baseline", "P2_gray"]
max_sources_per_split = 3
[dataset]
seed = 7
sources_per_split = { dev = 10, val = 10, test = 10 }
[execution]
workers = 1
ocr_timeout_seconds = 5
"""


def _config(**changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(json.dumps(BASE_CONFIG))
    raw.update(changes)
    return raw


SIZES = BASE_CONFIG["dataset"]["sources_per_split"]


# ------------------------------------------------------------------ configuration


def test_valid_config_parses() -> None:
    config = experiments.parse_config(_config())
    assert config.workers == 1
    assert config.conditions == ("clean", "blur_1")
    assert config.dataset.sources_per_split == {"dev": 10, "val": 10, "test": 10}


def test_all_conditions_shorthand() -> None:
    config = experiments.parse_config(_config(conditions="all"))
    assert len(config.conditions) == 16


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"experiment_id": "bad id!"}, "experiment_id"),
        ({"splits": ["holdout"]}, "splits"),
        ({"splits": []}, "splits"),
        ({"conditions": ["sepia"]}, "conditions"),
        ({"strategies": ["P9_magic"]}, "strategies"),
        ({"execution": {"workers": 64}}, "workers"),
        ({"execution": {"workers": 1, "ocr_timeout_seconds": 600}}, "timeout"),
        ({"max_sources_per_split": 0}, "max_sources_per_split"),
        ({"dataset": {"seed": 1, "sources_per_split": {"dev": 5}}}, "sources_per_split"),
        ({"dataset": {"seed": "x", "sources_per_split": SIZES}}, "seed"),
    ],
)  # fmt: skip
def test_invalid_configs_are_rejected(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(experiments.ConfigError, match=message):
        experiments.parse_config(_config(**changes))


def test_missing_key_is_reported() -> None:
    raw = _config()
    del raw["strategies"]
    with pytest.raises(experiments.ConfigError, match="strategies"):
        experiments.parse_config(raw)


def test_load_config_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "unit.toml"
    path.write_text(TOML, encoding="utf-8")
    config = experiments.load_config(path)
    assert config.experiment_id == "unit_test"
    assert config.source_path == path


def test_task_enumeration_is_bounded_and_complete() -> None:
    config = experiments.parse_config(_config())
    dataset = build_dataset(config.dataset)
    tasks = list(config.tasks(dataset))
    assert len(tasks) == 3 * 2 * 2  # sources x conditions x strategies
    assert {s.split for s, _, _ in tasks} == {"dev"}


# ------------------------------------------------------------------ runner


class FakeEngine:
    """Replaces ocr.recognize: perfect transcript of a fixed card, or a timeout."""

    def __init__(self, text: str, timeout_on: int | None = None) -> None:
        self.text = text
        self.calls = 0
        self.timeout_on = timeout_on

    def __call__(self, image: Image.Image, **kwargs: object) -> str:
        self.calls += 1
        if self.timeout_on == self.calls:
            raise ocr.OCRTimeoutError("OCR timed out.")
        return self.text


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "unit.toml"
    path.write_text(TOML, encoding="utf-8")
    return path


def test_run_records_every_task_including_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, config_file: Path
) -> None:
    engine = FakeEngine("Name: Ana Lima", timeout_on=2)
    monkeypatch.setattr(ocr, "recognize", engine)
    config = experiments.load_config(config_file)
    out = experiments.run_experiment(config, root=tmp_path, environment_label="unit")
    rows = experiments.read_observations(out / "observations.csv")
    assert len(rows) == 12
    assert [r["status"] for r in rows].count("timeout") == 1
    assert all(float(r["ocr_ms"]) >= 0 for r in rows)
    manifest = experiments.manifest_dir(tmp_path, config.dataset)
    assert (manifest / "sources.csv").exists()
    assert (manifest / "trials.csv").exists()


def test_run_resumes_without_repeating_tasks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, config_file: Path
) -> None:
    engine = FakeEngine("text")
    monkeypatch.setattr(ocr, "recognize", engine)
    config = experiments.load_config(config_file)
    out = experiments.run_experiment(config, root=tmp_path)
    # Simulate an interruption: keep only the first 5 observations.
    path = out / "observations.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:6]) + "\n", encoding="utf-8")
    engine.calls = 0
    experiments.run_experiment(config, root=tmp_path)
    assert engine.calls == 7
    rows = experiments.read_observations(path)
    assert len(rows) == 12
    assert len({r["task_id"] for r in rows}) == 12
    runs = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))["runs"]
    assert [r["tasks_run"] for r in runs] == [12, 7]


def test_run_metadata_records_provenance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, config_file: Path
) -> None:
    monkeypatch.setattr(ocr, "recognize", FakeEngine("text"))
    config = experiments.load_config(config_file)
    out = experiments.run_experiment(config, root=tmp_path, environment_label="unit-label")
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    env = meta["runs"][0]["environment"]
    assert meta["config_sha256"]
    assert meta["dataset"]["seed"] == 7
    assert len(meta["dataset"]["fingerprint"]) == 64
    assert env["environment_label"] == "unit-label"
    assert env["omp_thread_limit"] == "1"
    for key in ("git_commit", "python", "platform", "tesseract_version", "packages"):
        assert key in env


def test_run_task_measures_and_renders_real_images(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Image.Image] = []

    def capture(image: Image.Image, **_: object) -> str:
        seen.append(image)
        return "x"

    monkeypatch.setattr(ocr, "recognize", capture)
    config = experiments.parse_config(_config(strategies=["P5_upscale2"], conditions=["res_0.45"]))
    source = build_dataset(config.dataset).sources[0]
    row = experiments.run_task(experiments.Task("t", source, "res_0.45", "P5_upscale2", 7, 5.0))
    assert row["status"] == "ok"
    assert (row["width"], row["height"]) == seen[0].size
    assert seen[0].size == (round(900 * 0.45) * 2, round(520 * 0.45) * 2)


# ------------------------------------------------------------------ evaluation


def _rows_for(dataset: Any, perfect: bool) -> list[dict[str, str]]:
    rows = []
    for source in dataset.sources_in("dev")[:4]:
        text = "\n".join(source.ground_truth()) if perfect else "unreadable"
        rows.append(
            {
                "task_id": f"{source.source_id}|clean|P0_baseline",
                "source_id": source.source_id,
                "split": "dev",
                "condition": "clean",
                "strategy": "P0_baseline",
                "status": "ok",
                "ocr_text": text,
                "preprocess_ms": "1.0",
                "ocr_ms": "100.0",
            }
        )
    return rows


@pytest.fixture(scope="module")
def small_dataset() -> Any:
    return build_dataset(DatasetSpec(seed=7, sources_per_split={"dev": 10, "val": 10, "test": 10}))


def test_perfect_transcripts_give_zero_error_and_perfect_matching(small_dataset: Any) -> None:
    observations, scores = evaluation.compute(small_dataset, _rows_for(small_dataset, True))
    summary = evaluation.summarize(observations, scores, tau=0.0, seed=1)
    ocr_pooled = summary["ocr"]["dev/P0_baseline"]["pooled"]
    assert ocr_pooled["cer"]["estimate"] == 0.0
    assert ocr_pooled["exact_rate"]["estimate"] == 1.0
    assert ocr_pooled["name_token_recall"]["estimate"] == 1.0
    for matcher in ("M0_baseline", "M1_token_sequence", "M2_tolerant", "M3_confusable"):
        entry = summary["matching"]["dev/P0_baseline"]["pooled"][matcher]
        assert entry["frr"]["estimate"] == 0.0, matcher
        assert entry["far"]["estimate"] == 0.0, matcher
        assert (entry["tp"], entry["fn"]) == (4, 0)
        assert entry["fp"] + entry["tn"] == 12  # three negatives per source


def test_failed_ocr_counts_as_errors_and_rejections(small_dataset: Any) -> None:
    rows = _rows_for(small_dataset, True)
    for row in rows:
        row["status"] = "timeout"
    observations, scores = evaluation.compute(small_dataset, rows)
    summary = evaluation.summarize(observations, scores, tau=0.3, seed=1)
    pooled = summary["ocr"]["dev/P0_baseline"]["pooled"]
    assert pooled["status"]["timeout"] == 4
    assert pooled["cer"]["estimate"] == 1.0  # every reference character missing
    entry = summary["matching"]["dev/P0_baseline"]["pooled"]["M2_tolerant"]
    assert entry["frr"]["estimate"] == 1.0
    assert entry["far"]["estimate"] == 0.0


def test_tau_sweep_is_monotone_and_selection_follows_the_rule(small_dataset: Any) -> None:
    _, scores = evaluation.compute(small_dataset, _rows_for(small_dataset, True))
    sweep = evaluation.tau_sweep(scores)
    fars = [r["far"] for r in sweep]
    frrs = [r["frr"] for r in sweep]
    assert fars == sorted(fars)
    assert frrs == sorted(frrs, reverse=True)
    synthetic = [
        {"tau": 0.0, "far": 0.0},
        {"tau": 0.1, "far": 0.005},
        {"tau": 0.2, "far": 0.02},
        {"tau": 0.3, "far": 0.009},  # non-monotone on purpose: rule takes the largest eligible
    ]
    assert evaluation.select_tau(synthetic) == 0.3
    assert evaluation.select_tau([{"tau": 0.1, "far": 0.5}]) == 0.0


def test_paired_comparisons_cover_strategies_and_matchers(small_dataset: Any) -> None:
    rows = _rows_for(small_dataset, True)
    worse = [
        dict(r, strategy="P2_gray", ocr_text="garbled", task_id=r["task_id"] + "x") for r in rows
    ]
    observations, scores = evaluation.compute(small_dataset, rows + worse)
    summary = evaluation.summarize(observations, scores, tau=0.0, seed=1)
    delta = summary["paired"]["preprocessing_vs_P0"]["dev/P2_gray"]
    assert delta["n_pairs"] == 4
    assert delta["delta_cer"]["estimate"] > 0
    assert "M2_tolerant" in summary["paired"]["matchers_vs_M0"]["dev/P0_baseline"]


# ------------------------------------------------------------------ reporting and CLI


def test_report_without_results_is_marked_preliminary(tmp_path: Path) -> None:
    written = reporting.build_report(root=tmp_path)
    assert (tmp_path / reporting.RESULTS_MD) in written
    app = json.loads((tmp_path / reporting.APP_SUMMARY).read_text(encoding="utf-8"))
    assert app["status"] == "preliminary"
    assert "Not yet run" in (tmp_path / reporting.RESULTS_MD).read_text(encoding="utf-8")


def test_full_cli_pipeline_with_fake_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, config_file: Path
) -> None:
    monkeypatch.setattr(ocr, "recognize", FakeEngine("Name: Ana Lima"))
    script = runpy.run_path(str(experiments.REPO_ROOT / "scripts" / "run_research.py"))
    main = script["main"]
    root = ["--root", str(tmp_path)]
    assert main(["run", "--config", str(config_file), "--environment", "unit", *root]) == 0
    assert main(["evaluate", "--config", str(config_file), *root]) == 0
    summary = json.loads(
        (experiments.results_dir(tmp_path, "unit_test") / "summary.json").read_text("utf-8")
    )
    assert summary["experiment_id"] == "unit_test"
    assert summary["tau"] == 0.0  # no frozen selection in this root
    with (experiments.results_dir(tmp_path, "unit_test") / "observation_metrics.csv").open(
        encoding="utf-8"
    ) as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == 12
    assert main(["report", *root]) == 0


def test_full_report_from_all_three_experiments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Build E1-E3 outputs with a fake engine and check every table and figure is produced."""

    def engine(image: Image.Image, **_: object) -> str:
        # Wider images (upscaled) "read" better: lets the comparison have a winner.
        return "Name: Ana Lima" if image.width > 1000 else "Name: Ana"

    monkeypatch.setattr(ocr, "recognize", engine)
    configs = {
        "e1_degradation": {"splits": ["dev", "val"], "strategies": ["P0_baseline"]},
        "e2_preprocessing": {
            "splits": ["dev", "val"],
            "strategies": ["P0_baseline", "P5_upscale2"],
        },
        "e3_test": {"splits": ["test"], "strategies": ["P0_baseline", "P5_upscale2"]},
    }
    for experiment_id, changes in configs.items():
        raw = _config(experiment_id=experiment_id, max_sources_per_split=2, **changes)
        config = experiments.parse_config(raw)
        experiments.run_experiment(config, root=tmp_path, environment_label="unit")
        evaluation.evaluate_experiment(config, root=tmp_path, tau=0.25)
    selection = {"preprocessing": "P5_upscale2", "m2_tau": 0.25}
    (tmp_path / reporting.SELECTION).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / reporting.SELECTION).write_text(json.dumps(selection), encoding="utf-8")

    written = {p.name for p in reporting.build_report(root=tmp_path)}
    expected_figures = {
        "fig1_cer_by_condition.png",
        "fig2_preprocessing.png",
        "fig3_far_frr.png",
        "fig4_accuracy_latency.png",
        "fig5_latency_distribution.png",
        "fig6_confusion.png",
    }
    assert expected_figures <= written
    for name in expected_figures:
        assert (tmp_path / reporting.FIGURES_DIR / name).stat().st_size > 5_000
    results = (tmp_path / reporting.RESULTS_MD).read_text(encoding="utf-8")
    for heading in ("## E1", "## E2", "## E3", "## Frozen selection", "## Execution environment"):
        assert heading in results
    assert "Not yet run" not in results
    app = json.loads((tmp_path / reporting.APP_SUMMARY).read_text(encoding="utf-8"))
    assert app["status"] == "final"
    assert set(app["test_ocr"]) == {"test/P0_baseline", "test/P5_upscale2"}
    assert app["test_matching_P0"]["M2_tolerant"]["tau"] == 0.25


def test_observation_archive_is_byte_reproducible(tmp_path: Path) -> None:
    path = tmp_path / "observations.csv"
    path.write_text("task_id,status\na,ok\n", encoding="utf-8")
    first = experiments.archive_observations(path).read_bytes()
    second = experiments.archive_observations(path).read_bytes()
    assert first == second
    assert evaluation.load_observation_rows(tmp_path)[0]["task_id"] == "a"
    path.unlink()  # evaluation falls back to the committed archive
    assert evaluation.load_observation_rows(tmp_path)[0]["status"] == "ok"
