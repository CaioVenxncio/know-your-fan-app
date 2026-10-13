"""Read-only access to precomputed research results for the Streamlit app.

Standard library only: the app never imports the experiment machinery and never
runs OCR experiments. It only reads the versioned files produced by
``scripts/run_research.py report``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_PATH = Path("experiments") / "results" / "research_summary.json"
FIGURES_DIR = Path("docs") / "research" / "figures"
REPORT_PATH = "docs/research/report.md"
REPOSITORY_URL = "https://github.com/CaioVenxncio/know-your-fan-app"

# Figures shown in the app, in order, with captions.
FIGURES: tuple[tuple[str, str], ...] = (
    ("fig1_cer_by_condition.png", "Character error rate by degradation condition (test split)."),
    ("fig3_far_frr.png", "False acceptance vs false rejection for the matching strategies."),
    ("fig2_preprocessing.png", "Preprocessing strategies on the dev and val splits."),
)


@dataclass(frozen=True, slots=True)
class ResearchResults:
    summary: dict[str, Any] | None
    figures: list[tuple[Path, str]]

    @property
    def available(self) -> bool:
        return self.summary is not None

    @property
    def is_final(self) -> bool:
        return self.summary is not None and self.summary.get("status") == "final"


def load_results(root: Path | None = None) -> ResearchResults:
    """Load the app summary and the figures that exist. Never raises for missing files."""
    base = REPO_ROOT if root is None else root
    summary: dict[str, Any] | None = None
    path = base / SUMMARY_PATH
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = None
        summary = loaded if isinstance(loaded, dict) else None
    figures = [
        (base / FIGURES_DIR / name, caption)
        for name, caption in FIGURES
        if (base / FIGURES_DIR / name).is_file()
    ]
    return ResearchResults(summary, figures)


def _interval(entry: dict[str, Any] | None) -> str:
    if not entry or entry.get("estimate") is None:
        return "n/a"
    low, high = entry.get("ci_low"), entry.get("ci_high")
    if low is None or high is None:
        return f"{entry['estimate']:.3f}"
    return f"{entry['estimate']:.3f} [{low:.3f}, {high:.3f}]"


def ocr_rows(summary: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for key, entry in sorted(summary.get("test_ocr", {}).items()):
        rows.append(
            {
                "Preprocessing": key.split("/", 1)[1],
                "CER [95% CI]": _interval(entry.get("cer")),
                "WER [95% CI]": _interval(entry.get("wer")),
                "Name-token recall [95% CI]": _interval(entry.get("name_token_recall")),
                "Median latency (ms)": f"{entry.get('median_latency_ms', 0):.0f}",
                "Images / sources": f"{entry.get('n_observations')} / {entry.get('n_sources')}",
            }
        )
    return rows


def matching_rows(summary: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for matcher, entry in summary.get("test_matching_P0", {}).items():
        tau = entry.get("tau")
        rows.append(
            {
                "Matcher": matcher + (f" (τ={tau:.2f})" if tau is not None else ""),
                "FAR [95% CI]": _interval(entry.get("far")),
                "FRR [95% CI]": _interval(entry.get("frr")),
                "TP / FP / TN / FN": f"{entry.get('tp')} / {entry.get('fp')} / "
                f"{entry.get('tn')} / {entry.get('fn')}",
            }
        )
    return rows


EXPLORER_PATH = Path("experiments") / "results" / "research_explorer.json"
_REQUIRED_EXPLORER_KEYS = (
    "selection",
    "runs",
    "conditions",
    "test_ocr",
    "devval_preprocessing",
    "test_matching",
    "tau_sweep",
)


def load_explorer(root: Path | None = None) -> dict[str, Any] | None:
    """Load the precomputed interactive research data, or None if absent or malformed."""
    path = (REPO_ROOT if root is None else root) / EXPLORER_PATH
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(loaded, dict) or any(k not in loaded for k in _REQUIRED_EXPLORER_KEYS):
        return None
    return loaded


def total_ocr_runs(explorer: dict[str, Any]) -> int:
    return sum(int(run["ocr_runs"]) for run in explorer["runs"].values())


def study_scope(explorer: dict[str, Any]) -> dict[str, int]:
    """Headline scope figures, all read from the committed results (none hard-coded)."""
    devval = explorer["devval_preprocessing"]
    cards = (
        int(devval["dev"]["P0_baseline"]["n_sources"])
        + int(devval["val"]["P0_baseline"]["n_sources"])
        + int(explorer["test_ocr"]["P0_baseline"]["pooled"]["n_sources"])
    )
    return {
        "cards": cards,
        "ocr_runs": total_ocr_runs(explorer),
        "conditions": int(explorer["runs"]["e3_test"]["n_conditions"]),
        "matching_rules": len(explorer["test_matching"]["P0_baseline"]),
    }


def condition_rows(
    explorer: dict[str, Any], metric: str, family: str | None = None
) -> list[dict[str, Any]]:
    """Long-format rows (one per condition x strategy) for the test split."""
    families = {c["name"]: c["family"] for c in explorer["conditions"]}
    rows = []
    for strategy, data in explorer["test_ocr"].items():
        for condition, entry in data["by_condition"].items():
            if family and families[condition] != family:
                continue
            value = entry[metric]
            rows.append(
                {
                    "condition": condition,
                    "family": families[condition],
                    "strategy": strategy,
                    "estimate": value["estimate"],
                    "ci_low": value["ci_low"],
                    "ci_high": value["ci_high"],
                    "n_cards": entry["n_sources"],
                }
            )
    order = [c["name"] for c in explorer["conditions"]]
    return sorted(rows, key=lambda r: (order.index(r["condition"]), r["strategy"]))


def preprocessing_rows(explorer: dict[str, Any], metric: str) -> list[dict[str, Any]]:
    rows = []
    for split, strategies in explorer["devval_preprocessing"].items():
        for strategy, entry in strategies.items():
            value = entry[metric]
            rows.append(
                {
                    "split": split,
                    "strategy": strategy,
                    "estimate": value["estimate"],
                    "ci_low": value["ci_low"],
                    "ci_high": value["ci_high"],
                    "median_latency_ms": entry["median_latency_ms"],
                    "n_cards": entry["n_sources"],
                }
            )
    return rows


def sweep_rows(explorer: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "split": split,
            "tau": r["tau"],
            "far": r["far"],
            "frr": r["frr"],
            "n_negatives": r["n_negatives"],
            "n_positives": r["n_positives"],
        }
        for split, sweep in explorer["tau_sweep"].items()
        for r in sweep
    ]
