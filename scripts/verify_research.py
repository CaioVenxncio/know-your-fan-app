"""Verify the integrity of the committed Phase 4 research record (no OCR is run).

Checks, for every committed experiment:

* the configuration file still hashes to the ``config_sha256`` in its run metadata;
* the dataset rebuilt from the configuration has the recorded fingerprint, and the
  regenerated manifest matches the committed one (compared with LF line endings,
  because the repository normalizes text files to LF);
* the observation archive covers exactly the configured tasks, once each, all ``ok``;
* every run was recorded from a clean Git tree;
* E1 + E2 + E3 total 19,200 OCR runs;
* E3 ran only the test split with exactly the frozen preprocessing strategies, and the
  app-facing files carry the frozen selection.

All checks run on a temporary copy of ``experiments/`` and ``docs/research/`` that
leaves out local, untracked files (plain ``observations.csv``, derived summaries), so
only the committed archives are verified and the working tree is never modified.

With ``--reanalyse`` it also recomputes every metric from the committed observations
in that copy and compares the regenerated outputs with the committed ones:

* ``docs/research/results.md`` and ``research_summary.json`` must be byte-identical;
* ``research_explorer.json`` must be equal value for value, except matching latency,
  which is re-measured by design (see docs/research/report.md, section 11);
* figures are reported as byte-identical or not. PNG bytes depend on the Matplotlib
  build and fonts, so a difference is a warning unless ``--strict-figures`` is given.

Exit status 1 if any check fails. Usage:
    uv run python scripts/verify_research.py [--reanalyse] [--strict-figures]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from know_your_fan.research import dataset, evaluation, experiments, reporting

ROOT = experiments.REPO_ROOT
RESULTS = Path("experiments") / "results"
ALL_EXPERIMENTS = ("pilot", *reporting.EXPERIMENTS)
MAIN_RUNS = 19_200
RE_MEASURED = "matching_latency_us"


class Checker:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        self.failures += not passed
        print(("PASS " if passed else "FAIL ") + label + (f"  [{detail}]" if detail else ""))

    def warn(self, label: str) -> None:
        print("WARN " + label)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def verify_record(root: Path, checker: Checker) -> None:
    main_runs = 0
    manifests_done: set[Path] = set()
    for experiment in ALL_EXPERIMENTS:
        meta = _json(root / RESULTS / experiment / "run_metadata.json")
        config_path = root / meta["config_file"]
        digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
        checker.check(f"{experiment}: config hash matches", digest == meta["config_sha256"])
        config = experiments.load_config(config_path)
        built = dataset.build_dataset(config.dataset)
        checker.check(
            f"{experiment}: dataset fingerprint reproduces",
            built.fingerprint() == meta["dataset"]["fingerprint"],
        )
        manifest = experiments.manifest_dir(root, config.dataset)
        if manifest not in manifests_done:
            manifests_done.add(manifest)
            with tempfile.TemporaryDirectory() as tmp:
                fresh = dataset.write_manifest(built, Path(tmp))
                same = all(_lf(p) == _lf(manifest / p.name) for p in fresh)
            checker.check(f"manifest {manifest.name} regenerates identically (LF)", same)
        expected = {
            experiments.task_id(source.source_id, condition, strategy)
            for source, condition, strategy in config.tasks(built)
        }
        rows = evaluation.load_observation_rows(root / RESULTS / experiment)
        counts = Counter(row["task_id"] for row in rows)
        statuses = Counter(row["status"] for row in rows)
        checker.check(
            f"{experiment}: observations cover the configured tasks once each, all ok",
            set(counts) == expected and max(counts.values()) == 1 and set(statuses) == {"ok"},
            f"{len(counts)} tasks",
        )
        checker.check(
            f"{experiment}: recorded from a clean tree",
            not any(run["environment"]["git_dirty"] for run in meta["runs"]),
        )
        if experiment != "pilot":
            main_runs += len(counts)
    checker.check(f"E1+E2+E3 total {MAIN_RUNS:,} OCR runs", main_runs == MAIN_RUNS, str(main_runs))

    selection = _json(root / reporting.SELECTION)
    e3 = _json(root / RESULTS / "e3_test" / "run_metadata.json")["config"]
    checker.check("E3 ran only the test split", e3["splits"] == ["test"])
    checker.check(
        "E3 strategies are the frozen ones", e3["strategies"] == selection["e3_strategies"]
    )
    explorer = _json(root / RESULTS / "research_explorer.json")["selection"]
    summary = _json(root / reporting.APP_SUMMARY)["selection"]
    checker.check(
        "app-facing files carry the frozen selection",
        summary == selection
        and explorer
        == {"preprocessing": selection["preprocessing"], "m2_tau": selection["m2_tau"]},
    )


def _differences(new: Any, old: Any, path: str = "") -> list[str]:
    if isinstance(new, dict) and isinstance(old, dict):
        if set(new) != set(old):
            return [path or "/"]
        return [d for k in new for d in _differences(new[k], old[k], f"{path}/{k}")]
    if isinstance(new, list) and isinstance(old, list) and len(new) == len(old):
        return [d for i, (a, b) in enumerate(zip(new, old, strict=True)) for d in
                _differences(a, b, f"{path}[{i}]")]  # fmt: skip
    return [] if new == old else [path]


# Local, untracked files that must not stand in for the committed archives.
_UNTRACKED = shutil.ignore_patterns(
    "observations.csv", "summary.json", "observation_metrics.csv", "trial_scores.csv.gz"
)


def committed_copy(root: Path, destination: Path) -> Path:
    shutil.copytree(root / "experiments", destination / "experiments", ignore=_UNTRACKED)
    shutil.copytree(root / "docs" / "research", destination / "docs" / "research")
    return destination


def verify_reanalysis(root: Path, copy: Path, checker: Checker, *, strict_figures: bool) -> None:
    """Re-evaluate in ``copy`` and compare the regenerated outputs with ``root``."""
    for experiment in reporting.EXPERIMENTS:
        config = experiments.load_config(copy / "experiments" / "configs" / f"{experiment}.toml")
        evaluation.evaluate_experiment(config, root=copy)
    reporting.build_report(root=copy)
    reporting.export_explorer(root=copy)

    for relative in (reporting.RESULTS_MD, reporting.APP_SUMMARY):
        checker.check(
            f"re-analysis: {relative.as_posix()} byte-identical",
            (copy / relative).read_bytes() == (root / relative).read_bytes(),
        )
    explorer = RESULTS / "research_explorer.json"
    changed = _differences(_json(copy / explorer), _json(root / explorer))
    unexpected = [d for d in changed if not d.startswith(f"/{RE_MEASURED}")]
    checker.check(
        "re-analysis: research_explorer.json equal except re-measured matching latency",
        not unexpected,
        ", ".join(unexpected[:5]),
    )
    for figure in sorted((root / reporting.FIGURES_DIR).glob("*.png")):
        same = (copy / reporting.FIGURES_DIR / figure.name).read_bytes() == figure.read_bytes()
        label = f"re-analysis: figure {figure.name} byte-identical"
        if same or strict_figures:
            checker.check(label, same)
        else:
            checker.warn(f"{label}: no (PNG bytes depend on the Matplotlib build and fonts)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--reanalyse", action="store_true", help="recompute metrics and compare")
    parser.add_argument("--strict-figures", action="store_true", help="fail on figure differences")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    checker = Checker()
    with tempfile.TemporaryDirectory() as tmp:
        copy = committed_copy(args.root, Path(tmp))
        verify_record(copy, checker)
        if args.reanalyse:
            verify_reanalysis(args.root, copy, checker, strict_figures=args.strict_figures)
    print("research record verified" if not checker.failures else f"{checker.failures} FAILED")
    return 1 if checker.failures else 0


if __name__ == "__main__":
    sys.exit(main())
