"""Configuration-driven, resumable OCR experiment runner with provenance.

An experiment runs every (source, condition, strategy) task of its config and
appends one row per task to ``observations.csv`` as soon as it finishes, so an
interrupted run resumes where it stopped. Work is bounded: at most
``MAX_WORKERS`` processes, each limited to one Tesseract/OpenMP thread, and
every OCR call has a timeout. Failures and timeouts are recorded, never dropped.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import tomllib
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import pytesseract

from know_your_fan import ocr
from know_your_fan.research import degradations, preprocessing
from know_your_fan.research.dataset import (
    SPLITS,
    Dataset,
    DatasetSpec,
    Source,
    build_dataset,
    write_manifest,
)

MAX_WORKERS = 4
MAX_SOURCES_PER_SPLIT = 1000
OBSERVATION_FIELDS = [
    "task_id",
    "source_id",
    "split",
    "condition",
    "strategy",
    "status",
    "ocr_text",
    "width",
    "height",
    "render_ms",
    "degrade_ms",
    "preprocess_ms",
    "ocr_ms",
]
REPO_ROOT = Path(__file__).resolve().parents[3]


class ConfigError(ValueError):
    """The experiment configuration is invalid."""


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    experiment_id: str
    description: str
    splits: tuple[str, ...]
    conditions: tuple[str, ...]
    strategies: tuple[str, ...]
    dataset: DatasetSpec
    workers: int
    ocr_timeout_seconds: float
    max_sources_per_split: int | None
    source_path: Path | None = None

    def tasks(self, dataset: Dataset) -> Iterator[tuple[Source, str, str]]:
        for split in self.splits:
            sources = dataset.sources_in(split)[: self.max_sources_per_split]
            for source in sources:
                for condition in self.conditions:
                    for strategy in self.strategies:
                        yield source, condition, strategy


def _require(table: dict[str, Any], key: str, kind: type) -> Any:
    if key not in table:
        raise ConfigError(f"missing required key {key!r}")
    value = table[key]
    if not isinstance(value, kind) or (isinstance(value, bool) and kind is not bool):
        raise ConfigError(f"{key!r} must be of type {kind.__name__}")
    return value


def parse_config(raw: dict[str, Any], source_path: Path | None = None) -> ExperimentConfig:
    experiment_id = _require(raw, "experiment_id", str)
    if not experiment_id.replace("_", "").replace("-", "").isalnum():
        raise ConfigError("experiment_id may contain only letters, digits, '-' and '_'")
    splits = tuple(_require(raw, "splits", list))
    if not splits or any(s not in SPLITS for s in splits):
        raise ConfigError(f"splits must be a non-empty subset of {SPLITS}")
    conditions_raw = raw.get("conditions", "all")
    conditions = (
        tuple(degradations.CONDITIONS) if conditions_raw == "all" else tuple(conditions_raw)
    )
    unknown = [c for c in conditions if c not in degradations.CONDITIONS]
    if not conditions or unknown:
        raise ConfigError(f"unknown or empty conditions: {unknown}")
    strategies = tuple(_require(raw, "strategies", list))
    unknown = [s for s in strategies if s not in preprocessing.STRATEGIES]
    if not strategies or unknown:
        raise ConfigError(f"unknown or empty strategies: {unknown}")
    dataset_table = _require(raw, "dataset", dict)
    sizes = _require(dataset_table, "sources_per_split", dict)
    if set(sizes) != set(SPLITS) or not all(
        isinstance(n, int) and 1 <= n <= MAX_SOURCES_PER_SPLIT for n in sizes.values()
    ):
        raise ConfigError(
            f"sources_per_split must give 1..{MAX_SOURCES_PER_SPLIT} sources for each of {SPLITS}"
        )
    spec = DatasetSpec(
        seed=_require(dataset_table, "seed", int),
        sources_per_split=dict(sizes),
        version=dataset_table.get("version", DatasetSpec(seed=0).version),
    )
    execution = raw.get("execution", {})
    workers = execution.get("workers", 2)
    if not isinstance(workers, int) or not 1 <= workers <= MAX_WORKERS:
        raise ConfigError(f"execution.workers must be an integer in 1..{MAX_WORKERS}")
    timeout = float(execution.get("ocr_timeout_seconds", ocr.OCR_TIMEOUT_SECONDS))
    if not 1 <= timeout <= 60:
        raise ConfigError("execution.ocr_timeout_seconds must be in 1..60")
    limit = raw.get("max_sources_per_split")
    if limit is not None and (not isinstance(limit, int) or limit < 1):
        raise ConfigError("max_sources_per_split must be a positive integer")
    return ExperimentConfig(
        experiment_id=experiment_id,
        description=str(raw.get("description", "")),
        splits=splits,
        conditions=conditions,
        strategies=strategies,
        dataset=spec,
        workers=workers,
        ocr_timeout_seconds=timeout,
        max_sources_per_split=limit,
        source_path=source_path,
    )


def load_config(path: Path) -> ExperimentConfig:
    with path.open("rb") as handle:
        return parse_config(tomllib.load(handle), source_path=path)


# ---------------------------------------------------------------- provenance


def _relative(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
            [git, *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _tessdata_dir() -> Path | None:
    prefix = os.environ.get("TESSDATA_PREFIX")
    if prefix:
        return Path(prefix)
    try:
        output = subprocess.run(  # noqa: S603 - fixed arguments, no shell
            [pytesseract.pytesseract.tesseract_cmd, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first = (output.stdout or output.stderr).splitlines()[:1]
    if first and '"' in first[0]:
        return Path(first[0].split('"')[1])
    return None


def redact_home(path: Path) -> str:
    """Path with the user's home directory replaced by ``~`` (no username in provenance)."""
    resolved = Path(path).expanduser()
    try:
        return "~/" + resolved.relative_to(Path.home()).as_posix()
    except ValueError:
        return resolved.as_posix()


def capture_environment(label: str) -> dict[str, Any]:
    """Software, hardware, and data provenance for one experiment run."""
    tessdata = _tessdata_dir()
    models: dict[str, str] = {}
    if tessdata is not None:
        for language in ("eng", "por"):
            path = tessdata / f"{language}.traineddata"
            if path.exists():
                models[language] = _sha256(path)
    try:
        tesseract_version = str(pytesseract.get_tesseract_version())
        languages = sorted(pytesseract.get_languages(config=""))
    except (OSError, pytesseract.TesseractNotFoundError):
        tesseract_version, languages = "unavailable", []
    # Run outputs (results and the generated dataset manifests) do not count as "dirty".
    dirty = _git(
        "status",
        "--porcelain",
        "--",
        ".",
        ":(exclude)experiments/results",
        ":(exclude)experiments/manifests",
    )
    return {
        "environment_label": label,
        "ci": os.environ.get("GITHUB_ACTIONS") == "true",
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(dirty) if dirty is not None else None,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "tesseract_version": tesseract_version,
        "tesseract_languages": languages,
        "ocr_language_setting": ocr.OCR_LANGUAGE,
        "tessdata_dir": redact_home(tessdata) if tessdata else None,
        "traineddata_sha256": models,
        "omp_thread_limit": os.environ.get("OMP_THREAD_LIMIT"),
        "packages": {
            name: metadata.version(name) for name in ("pillow", "pytesseract", "numpy", "streamlit")
        },
    }


# ---------------------------------------------------------------- execution


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    source: Source
    condition: str
    strategy: str
    dataset_seed: int
    timeout_seconds: float


def _init_worker() -> None:
    ocr.limit_engine_threads()


def run_task(task: Task) -> dict[str, Any]:
    """Render, degrade, preprocess, and OCR one sample. Never raises for OCR failures."""
    started = time.perf_counter()
    card = ocr.render_specimen(task.source.profile())
    rendered = time.perf_counter()
    degradation = degradations.CONDITIONS[task.condition]
    seed = degradations.noise_seed(task.dataset_seed, task.source.source_id, task.condition)
    degraded = degradations.apply(card, degradation, seed)
    degraded_at = time.perf_counter()
    prepared = preprocessing.STRATEGIES[task.strategy](degraded)
    prepared_at = time.perf_counter()
    status, text = "ok", ""
    try:
        text = ocr.recognize(prepared, timeout_seconds=task.timeout_seconds)
    except ocr.OCRTimeoutError:
        status = "timeout"
    except (ocr.OCRFailedError, ocr.InvalidImageError):
        status = "failed"
    finished = time.perf_counter()
    return {
        "task_id": task.task_id,
        "source_id": task.source.source_id,
        "split": task.source.split,
        "condition": task.condition,
        "strategy": task.strategy,
        "status": status,
        "ocr_text": text,
        "width": prepared.width,
        "height": prepared.height,
        "render_ms": round((rendered - started) * 1000, 3),
        "degrade_ms": round((degraded_at - rendered) * 1000, 3),
        "preprocess_ms": round((prepared_at - degraded_at) * 1000, 3),
        "ocr_ms": round((finished - prepared_at) * 1000, 3),
    }


def task_id(source_id: str, condition: str, strategy: str) -> str:
    return f"{source_id}|{condition}|{strategy}"


def manifest_dir(root: Path, spec: DatasetSpec) -> Path:
    return root / "experiments" / "manifests" / f"{spec.version}-seed{spec.seed}"


def results_dir(root: Path, experiment_id: str) -> Path:
    return root / "experiments" / "results" / experiment_id


def read_observations(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def archive_observations(path: Path) -> Path:
    """Write a byte-reproducible gzip copy (``mtime=0``) of the observations CSV.

    The gzip file is what gets committed; the plain CSV stays local for resuming.
    """
    target = path.with_name(path.name + ".gz")
    with (
        path.open("rb") as raw,
        target.open("wb") as packed_file,
        gzip.GzipFile(filename="", mode="wb", fileobj=packed_file, mtime=0) as packed,
    ):
        shutil.copyfileobj(raw, packed)
    return target


def run_experiment(
    config: ExperimentConfig,
    *,
    root: Path = REPO_ROOT,
    environment_label: str = "local",
    progress_every: int = 250,
) -> Path:
    """Run (or resume) an experiment; returns its results directory."""
    dataset = build_dataset(config.dataset)
    write_manifest(dataset, manifest_dir(root, config.dataset))
    out = results_dir(root, config.experiment_id)
    out.mkdir(parents=True, exist_ok=True)
    observations_path = out / "observations.csv"
    done = {row["task_id"] for row in read_observations(observations_path)}
    tasks = [
        Task(
            task_id(source.source_id, condition, strategy),
            source,
            condition,
            strategy,
            config.dataset.seed,
            config.ocr_timeout_seconds,
        )
        for source, condition, strategy in config.tasks(dataset)
    ]
    pending = [t for t in tasks if t.task_id not in done]
    ocr.limit_engine_threads()  # workers inherit it; recorded in the environment below
    environment = capture_environment(environment_label)
    started = datetime.now(UTC).isoformat(timespec="seconds")
    wall = time.perf_counter()
    new_file = not observations_path.exists()
    completed = 0
    with observations_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OBSERVATION_FIELDS)
        if new_file:
            writer.writeheader()

        def record(row: dict[str, Any]) -> None:
            nonlocal completed
            writer.writerow(row)
            handle.flush()
            completed += 1
            if completed % progress_every == 0:
                print(f"  {config.experiment_id}: {len(done) + completed}/{len(tasks)}")

        if config.workers == 1:
            # In-process execution: simplest to debug, and test doubles apply.
            _init_worker()
            for task in pending:
                record(run_task(task))
        else:
            with ProcessPoolExecutor(max_workers=config.workers, initializer=_init_worker) as pool:
                in_flight: set[Future[dict[str, Any]]] = set()
                # At most 2x workers tasks in flight: bounded memory, no large backlog.
                for task in pending:
                    in_flight.add(pool.submit(run_task, task))
                    if len(in_flight) >= config.workers * 2:
                        finished, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
                        for future in finished:
                            record(future.result())
                for future in in_flight:
                    record(future.result())
    if completed or not (out / "observations.csv.gz").exists():
        archive_observations(observations_path)
    metadata_path = out / "run_metadata.json"
    runs: list[dict[str, Any]] = []
    if metadata_path.exists():
        runs = json.loads(metadata_path.read_text(encoding="utf-8")).get("runs", [])
    runs.append(
        {
            "started_utc": started,
            "wall_seconds": round(time.perf_counter() - wall, 2),
            "tasks_run": completed,
            "tasks_total": len(tasks),
            "environment": environment,
        }
    )
    payload = {
        "experiment_id": config.experiment_id,
        "description": config.description,
        "config_file": _relative(config.source_path, root),
        "config_sha256": _sha256(config.source_path) if config.source_path else None,
        "config": {
            "splits": list(config.splits),
            "conditions": list(config.conditions),
            "strategies": list(config.strategies),
            "workers": config.workers,
            "ocr_timeout_seconds": config.ocr_timeout_seconds,
            "max_sources_per_split": config.max_sources_per_split,
        },
        "dataset": {
            **asdict(config.dataset),
            "fingerprint": dataset.fingerprint(),
            "excluded_trials": dataset.excluded_trials,
        },
        "runs": runs,
    }
    metadata_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return out
