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
