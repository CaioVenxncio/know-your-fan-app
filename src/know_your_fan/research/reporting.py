"""Tables and figures generated from stored experiment results (no OCR is run).

Reads ``summary.json`` / ``observation_metrics.csv`` of the main experiments and
``experiments/configs/frozen_selection.json``, then writes:

* ``docs/research/results.md``: generated result tables (do not edit by hand);
* ``docs/research/figures/*.png``: figures;
* ``experiments/results/research_summary.json``: compact summary for the app.

Experiments that have not been run yet are skipped and listed as missing.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from know_your_fan.research import degradations
from know_your_fan.research.experiments import REPO_ROOT, results_dir

EXPERIMENTS = ("e1_degradation", "e2_preprocessing", "e3_test")
FIGURES_DIR = Path("docs") / "research" / "figures"
RESULTS_MD = Path("docs") / "research" / "results.md"
APP_SUMMARY = Path("experiments") / "results" / "research_summary.json"
SELECTION = Path("experiments") / "configs" / "frozen_selection.json"

# Okabe-Ito colour-blind-safe palette.
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]
MATCHER_LABELS = {
    "M0_baseline": "M0 baseline",
    "M1_token_sequence": "M1 token sequence",
    "M2_tolerant": "M2 tolerant",
    "M3_confusable": "M3 confusable",
}


def _load(root: Path, experiment: str) -> dict[str, Any] | None:
    path = results_dir(root, experiment) / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _metadata(root: Path, experiment: str) -> dict[str, Any] | None:
    path = results_dir(root, experiment) / "run_metadata.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _ci(entry: dict[str, Any], digits: int = 3) -> str:
    if entry.get("estimate") is None:
        return "n/a"
    return (
        f"{_fmt(entry['estimate'], digits)} "
        f"[{_fmt(entry['ci_low'], digits)}, {_fmt(entry['ci_high'], digits)}]"
    )


def _condition_order() -> list[str]:
    return list(degradations.CONDITIONS)


# ---------------------------------------------------------------- tables


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def ocr_condition_table(summary: dict[str, Any], key: str) -> str:
    by_condition = summary["ocr"][key]["by_condition"]
    rows = []
    for condition in _condition_order():
        if condition not in by_condition:
            continue
        entry = by_condition[condition]
        rows.append(
            [
                condition,
                str(entry["n_observations"]),
                _ci(entry["cer"]),
                _ci(entry["wer"]),
                _fmt(entry["exact_rate"]["estimate"]),
                _ci(entry["name_token_recall"]),
                str(entry["status"]["timeout"] + entry["status"]["failed"]),
            ]
        )
    return _table(
        ["Condition", "n", "CER [95% CI]", "WER [95% CI]", "Exact", "Name-token recall", "Failed"],
        rows,
    )


def preprocessing_table(summary: dict[str, Any], split: str) -> str:
    rows = []
    for key, entry in summary["ocr"].items():
        s, strategy = key.split("/")
        if s != split:
            continue
        pooled = entry["pooled"]
        paired = summary["paired"]["preprocessing_vs_P0"].get(key)
        rows.append(
            [
                strategy,
                str(pooled["n_observations"]),
                _ci(pooled["cer"]),
                _ci(paired["delta_cer"], 4) if paired else "reference",
                _ci(pooled["name_token_recall"]),
                _fmt(pooled["latency_ms"]["preprocess_plus_ocr"]["median"], 0),
                _fmt(pooled["latency_ms"]["preprocess_plus_ocr"]["p95"], 0),
            ]
        )
    return _table(
        [
            "Strategy",
            "n",
            "CER [95% CI]",
            "ΔCER vs P0 [95% CI]",
            "Name-token recall",
            "Median ms",
            "p95 ms",
        ],
        rows,
    )


def matching_table(summary: dict[str, Any], key: str) -> str:
    pooled = summary["matching"][key]["pooled"]
    paired = summary["paired"]["matchers_vs_M0"].get(key, {})
    rows = []
    for matcher, label in MATCHER_LABELS.items():
        entry = pooled[matcher]
        kinds = entry["far_by_negative_kind"]
        delta = paired.get(matcher)
        rows.append(
            [
                label + (f" (τ={entry['tau']:.2f})" if entry["tau"] is not None else ""),
                f"{entry['tp']}/{entry['fp']}/{entry['tn']}/{entry['fn']}",
                _ci(entry["far"], 4),
                _ci(entry["frr"]),
                _fmt(entry["precision"]),
                _fmt(entry["f1"]),
                " / ".join(_fmt(kinds[k]["far"], 4) for k in ("easy", "token_swap", "near_miss")),
                _ci(delta["delta_frr"], 4) if delta else "reference",
            ]
        )
    return _table(
        [
            "Matcher",
            "TP/FP/TN/FN",
            "FAR [95% CI]",
            "FRR [95% CI]",
            "Precision",
            "F1",
            "FAR easy / swap / near-miss",
            "ΔFRR vs M0 [95% CI]",
        ],
        rows,
    )


def environment_table(metadata: dict[str, Any]) -> str:
    env = metadata["runs"][-1]["environment"]
    languages = ", ".join(env["tesseract_languages"])
    models = "; ".join(f"{k}: {v[:16]}…" for k, v in env["traineddata_sha256"].items())
    packages = ", ".join(f"{k} {v}" for k, v in env["packages"].items())
    wall = sum(r["wall_seconds"] for r in metadata["runs"])
    rows = [
        ["Environment label", env["environment_label"]],
        ["Git commit (dirty)", f"{env['git_commit']} ({env['git_dirty']})"],
        ["Tesseract", env["tesseract_version"]],
        ["Languages / setting", f"{languages} / {env['ocr_language_setting']}"],
        ["Model SHA-256", models],
        ["OMP_THREAD_LIMIT", str(env["omp_thread_limit"])],
        ["Python / platform", f"{env['python']} / {env['platform']}"],
        ["CPU", f"{env['processor']} ({env['cpu_count']} logical)"],
        ["Packages", packages],
        ["Workers / wall time", f"{metadata['config']['workers']} / {wall:.0f} s"],
    ]
    return _table(["Item", "Value"], rows)


# ---------------------------------------------------------------- figures


def _pyplot() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 110,
            "savefig.bbox": "tight",
        }
    )
    return plt


def _errorbar(entry: dict[str, Any]) -> tuple[float, float, float]:
    estimate = entry["estimate"] or 0.0
    low = entry["ci_low"] if entry["ci_low"] is not None else estimate
    high = entry["ci_high"] if entry["ci_high"] is not None else estimate
    return estimate, estimate - low, high - estimate


def figure_cer_by_condition(summary: dict[str, Any], keys: list[str], path: Path) -> None:
    plt = _pyplot()
    conditions = [c for c in _condition_order() if c in summary["ocr"][keys[0]]["by_condition"]]
    fig, ax = plt.subplots(figsize=(10, 4))
    width = 0.8 / len(keys)
    for i, key in enumerate(keys):
        by_condition = summary["ocr"][key]["by_condition"]
        xs = [c_index + (i - (len(keys) - 1) / 2) * width for c_index in range(len(conditions))]
        values = [_errorbar(by_condition[c]["cer"]) for c in conditions]
        n_sources = by_condition[conditions[0]]["n_sources"]
        ax.bar(
            xs,
            [v[0] for v in values],
            width=width,
            yerr=[[v[1] for v in values], [v[2] for v in values]],
            color=PALETTE[i],
            capsize=2,
            label=f"{key} (n={n_sources} sources per condition)",
        )
    ax.set_xticks(range(len(conditions)), conditions, rotation=45, ha="right")
    ax.set_ylabel("Character error rate (micro), 95% bootstrap CI")
    ax.set_ylim(bottom=0)
    ax.set_title("OCR character error rate by degradation condition")
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(path)
    plt.close(fig)


def figure_preprocessing(summary: dict[str, Any], path: Path) -> None:
    plt = _pyplot()
    splits = sorted({k.split("/")[0] for k in summary["ocr"]})
    strategies = sorted({k.split("/")[1] for k in summary["ocr"]})
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, split in enumerate(splits):
        values = [_errorbar(summary["ocr"][f"{split}/{s}"]["pooled"]["cer"]) for s in strategies]
        n = summary["ocr"][f"{split}/{strategies[0]}"]["pooled"]["n_sources"]
        offsets = [j + (i - (len(splits) - 1) / 2) * 0.3 for j in range(len(strategies))]
        ax.errorbar(
            offsets,
            [v[0] for v in values],
            yerr=[[v[1] for v in values], [v[2] for v in values]],
            fmt="o",
            color=PALETTE[i],
            capsize=3,
            label=f"{split} (n={n} sources)",
        )
    ax.set_xticks(range(len(strategies)), strategies, rotation=30, ha="right")
    ax.set_ylabel("Pooled CER (micro), 95% bootstrap CI")
    ax.set_ylim(bottom=0)
    ax.set_title("Preprocessing strategies (pooled over the E2 conditions)")
    ax.legend(frameon=False)
    fig.savefig(path)
    plt.close(fig)


def figure_far_frr(
    curves: dict[str, list[dict[str, Any]]], points: dict[str, Any], path: Path
) -> None:
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for i, (label, sweep) in enumerate(curves.items()):
        ax.plot(
            [r["far"] for r in sweep],
            [r["frr"] for r in sweep],
            marker="o",
            color=PALETTE[i],
            label=(
                f"M2 τ sweep, {label} "
                f"(n_neg={sweep[0]['n_negatives']}, n_pos={sweep[0]['n_positives']})"
            ),
        )
        for r in sweep[:: max(1, len(sweep) // 4)]:
            ax.annotate(
                f"τ={r['tau']:.2f}",
                (r["far"], r["frr"]),
                fontsize=7,
                xytext=(3, 3),
                textcoords="offset points",
            )
    for j, (label, entry) in enumerate(points.items()):
        ax.scatter(
            entry["far"]["estimate"],
            entry["frr"]["estimate"],
            marker="s",
            color=PALETTE[3 + j],
            label=label,
            zorder=3,
        )
    ax.set_xlabel("False acceptance rate (negative trials)")
    ax.set_ylabel("False rejection rate (positive trials)")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.set_title("FAR vs FRR: matching strategies")
    ax.legend(frameon=False, fontsize=7)
    fig.savefig(path)
    plt.close(fig)


def figure_accuracy_latency(summary: dict[str, Any], split: str, path: Path) -> None:
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for i, (key, entry) in enumerate(sorted(summary["ocr"].items())):
        if not key.startswith(f"{split}/"):
            continue
        pooled = entry["pooled"]
        latency = pooled["latency_ms"]["preprocess_plus_ocr"]["median"]
        cer = pooled["cer"]["estimate"]
        ax.scatter(latency, cer, color=PALETTE[i % len(PALETTE)], s=40)
        ax.annotate(
            key.split("/")[1], (latency, cer), fontsize=8, xytext=(4, 2), textcoords="offset points"
        )
    ax.set_xlabel("Median preprocessing + OCR latency per image (ms)")
    ax.set_ylabel("Pooled CER (micro)")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.set_title(f"Accuracy vs latency ({split} split)")
    fig.savefig(path)
    plt.close(fig)


def figure_latency_distribution(observation_csv: Path, split: str, path: Path) -> None:
    plt = _pyplot()
    latencies: dict[str, list[float]] = defaultdict(list)
    with observation_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["split"] == split:
                latencies[row["strategy"]].append(
                    float(row["preprocess_ms"]) + float(row["ocr_ms"])
                )
    strategies = sorted(latencies)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.boxplot([latencies[s] for s in strategies], showfliers=False)
    ax.set_xticks(
        range(1, len(strategies) + 1),
        [f"{s}\n(n={len(latencies[s])})" for s in strategies],
        rotation=30,
        ha="right",
        fontsize=8,
    )
    ax.set_ylabel("Preprocessing + OCR latency (ms)")
    ax.set_ylim(bottom=0)
    ax.set_title(f"Latency distribution per strategy ({split}; whiskers 1.5 IQR, outliers hidden)")
    fig.savefig(path)
    plt.close(fig)


def figure_confusion(entries: dict[str, Any], path: Path) -> None:
    plt = _pyplot()
    fig, axes = plt.subplots(1, len(entries), figsize=(3.2 * len(entries), 3.2))
    for ax, (label, entry) in zip(axes, entries.items(), strict=True):
        matrix = [[entry["tp"], entry["fn"]], [entry["fp"], entry["tn"]]]
        ax.imshow(matrix, cmap="Blues")
        for r in range(2):
            for c in range(2):
                ax.text(c, r, str(matrix[r][c]), ha="center", va="center", fontsize=11)
        ax.set_xticks([0, 1], ["accept", "reject"])
        ax.set_yticks([0, 1], ["true name", "other name"])
        ax.set_title(label, fontsize=9)
    fig.suptitle("Matching confusion matrices (test split, trials)")
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------- report


def build_report(root: Path = REPO_ROOT) -> list[Path]:
    """Regenerate figures, generated tables, and the app summary. Returns written paths."""
    figures = root / FIGURES_DIR
    figures.mkdir(parents=True, exist_ok=True)
    summaries = {e: _load(root, e) for e in EXPERIMENTS}
    metadata = {e: _metadata(root, e) for e in EXPERIMENTS}
    selection_path = root / SELECTION
    selection = (
        json.loads(selection_path.read_text(encoding="utf-8")) if selection_path.exists() else None
    )
    written: list[Path] = []
    sections = [
        "# Generated results",
        "",
        "> Generated by `scripts/run_research.py report` from stored results. Do not edit by hand.",
        "> All data is synthetic. These figures describe OCR text matching on fictional",
        "> specimen cards; they are not identity-verification performance.",
        "",
    ]
    missing = [e for e, s in summaries.items() if s is None]
    if missing:
        sections += [f"**Not yet run:** {', '.join(missing)}.", ""]

    e1, e2, e3 = summaries["e1_degradation"], summaries["e2_preprocessing"], summaries["e3_test"]
    if e1:
        sections += ["## E1: degradations with the baseline pipeline (dev, val)", ""]
        for split in ("dev", "val"):
            sections += [
                f"### {split} / P0_baseline",
                "",
                ocr_condition_table(e1, f"{split}/P0_baseline"),
                "",
            ]
        sections += [
            "### Matching (dev, P0, pooled over conditions)",
            "",
            matching_table(e1, "dev/P0_baseline"),
            "",
        ]
    if e2:
        sections += ["## E2: preprocessing comparison (dev, val)", ""]
        for split in ("dev", "val"):
            sections += [f"### {split}", "", preprocessing_table(e2, split), ""]
        path = figures / "fig2_preprocessing.png"
        figure_preprocessing(e2, path)
        written.append(path)
        path = figures / "fig4_accuracy_latency.png"
        figure_accuracy_latency(e2, "dev", path)
        written.append(path)
        path = figures / "fig5_latency_distribution.png"
        figure_latency_distribution(
            results_dir(root, "e2_preprocessing") / "observation_metrics.csv", "dev", path
        )
        written.append(path)
    if selection:
        sections += [
            "## Frozen selection (made on dev/val before the test run)",
            "",
            "```json",
            json.dumps(selection, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    if e3 and selection:
        chosen = selection["preprocessing"]
        keys = ["test/P0_baseline"] + ([f"test/{chosen}"] if chosen != "P0_baseline" else [])
        sections += ["## E3: held-out test split", ""]
        for key in keys:
            sections += [f"### OCR, {key}", "", ocr_condition_table(e3, key), ""]
        if len(keys) > 1:
            sections += [
                "### Preprocessing, test (pooled)",
                "",
                preprocessing_table(e3, "test"),
                "",
            ]
        for key in keys:
            sections += [
                f"### Matching, {key} (pooled over conditions)",
                "",
                matching_table(e3, key),
                "",
            ]
        path = figures / "fig1_cer_by_condition.png"
        figure_cer_by_condition(e3, keys, path)
        written.append(path)
        curves = {"dev (E1, P0)": e1["tau_sweep"]["dev/P0_baseline"]} if e1 else {}
        curves["test (E3, P0)"] = e3["tau_sweep"]["test/P0_baseline"]
        pooled = e3["matching"]["test/P0_baseline"]["pooled"]
        points = {
            f"{MATCHER_LABELS[m]} (test, P0)": pooled[m]
            for m in ("M0_baseline", "M1_token_sequence", "M3_confusable")
        }
        path = figures / "fig3_far_frr.png"
        figure_far_frr(curves, points, path)
        written.append(path)
        path = figures / "fig6_confusion.png"
        figure_confusion({MATCHER_LABELS[m]: pooled[m] for m in MATCHER_LABELS}, path)
        written.append(path)
    available = {e: m for e, m in metadata.items() if m is not None}
    if available:
        sections += ["## Execution environment", ""]
        for experiment, meta in available.items():
            sections += [f"### {experiment}", "", environment_table(meta), ""]
    results_md = root / RESULTS_MD
    results_md.parent.mkdir(parents=True, exist_ok=True)
    results_md.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8", newline="\n")
    written.append(results_md)
    app_summary = root / APP_SUMMARY
    app_summary.parent.mkdir(parents=True, exist_ok=True)
    app_summary.write_text(
        json.dumps(_app_summary(summaries, selection), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    written.append(app_summary)
    return written


def _app_summary(summaries: dict[str, Any], selection: dict[str, Any] | None) -> dict[str, Any]:
    """A small, display-ready subset for the Streamlit research page."""
    e3 = summaries.get("e3_test")
    out: dict[str, Any] = {
        "status": "final" if e3 and selection else "preliminary",
        "experiments_available": [e for e, s in summaries.items() if s],
        "selection": selection,
    }
    if e3 and selection:
        chosen = selection["preprocessing"]
        out["test_ocr"] = {
            key: {
                "cer": e3["ocr"][key]["pooled"]["cer"],
                "wer": e3["ocr"][key]["pooled"]["wer"],
                "name_token_recall": e3["ocr"][key]["pooled"]["name_token_recall"],
                "median_latency_ms": e3["ocr"][key]["pooled"]["latency_ms"]["preprocess_plus_ocr"][
                    "median"
                ],
                "n_observations": e3["ocr"][key]["pooled"]["n_observations"],
                "n_sources": e3["ocr"][key]["pooled"]["n_sources"],
            }
            # Ordered (selected strategy, then baseline) so the file is byte-reproducible;
            # a set here made the key order depend on PYTHONHASHSEED.
            for key in dict.fromkeys((f"test/{chosen}", "test/P0_baseline"))
        }
        out["test_matching_P0"] = {
            m: {
                k: e3["matching"]["test/P0_baseline"]["pooled"][m][k]
                for k in ("far", "frr", "tp", "fp", "tn", "fn", "tau")
            }
            for m in MATCHER_LABELS
        }
    return out


# ---------------------------------------------------------------- explorer export

EXPLORER_PATH = Path("experiments") / "results" / "research_explorer.json"
_OCR_FIELDS = ("cer", "wer", "name_token_recall", "exact_rate")


def _ocr_entry(entry: dict[str, Any]) -> dict[str, Any]:
    latency = entry["latency_ms"]["preprocess_plus_ocr"]
    return {
        **{field: entry[field] for field in _OCR_FIELDS},
        "median_latency_ms": latency["median"],
        "p95_latency_ms": latency["p95"],
        "n_observations": entry["n_observations"],
        "n_sources": entry["n_sources"],
    }


def _matching_entry(entry: dict[str, Any]) -> dict[str, Any]:
    keys = ("tau", "tp", "fp", "tn", "fn", "far", "frr", "precision", "recall", "f1")
    return {
        **{k: entry[k] for k in keys},
        "far_by_negative_kind": entry["far_by_negative_kind"],
    }


def export_explorer(root: Path = REPO_ROOT) -> Path:
    """Write a compact, display-ready subset of the final results for the app.

    Values are copied verbatim from the experiment summaries (no new computation)
    and carry their sample sizes. Raises FileNotFoundError if a summary is missing.
    """
    summaries: dict[str, dict[str, Any]] = {}
    for experiment in EXPERIMENTS:
        loaded = _load(root, experiment)
        if loaded is None:
            raise FileNotFoundError(f"{experiment}/summary.json is missing; run `evaluate` first")
        summaries[experiment] = loaded
    e2, e3 = summaries["e2_preprocessing"], summaries["e3_test"]
    selection = json.loads((root / SELECTION).read_text(encoding="utf-8"))
    runs = {}
    for experiment in EXPERIMENTS:
        meta = _metadata(root, experiment)
        assert meta is not None  # noqa: S101 - a summary exists, so its metadata does
        env = meta["runs"][-1]["environment"]
        runs[experiment] = {
            "ocr_runs": sum(r["tasks_run"] for r in meta["runs"]),
            "splits": meta["config"]["splits"],
            "strategies": meta["config"]["strategies"],
            "n_conditions": len(meta["config"]["conditions"]),
            "git_commit": env["git_commit"],
            "tesseract_version": env["tesseract_version"],
            "dataset_fingerprint": meta["dataset"]["fingerprint"],
        }
    conditions = [
        {
            "name": name,
            "family": d.family,
            "blur_sigma": d.blur_sigma,
            "rotation_degrees": d.rotation_degrees,
            "noise_sigma": d.noise_sigma,
            "scale": d.scale,
        }
        for name, d in degradations.CONDITIONS.items()
    ]
    explorer = {
        "status": "final",
        "note": "Synthetic cards only. Copied from the Phase 4 summaries; see docs/research.",
        "selection": {"preprocessing": selection["preprocessing"], "m2_tau": selection["m2_tau"]},
        "runs": runs,
        "conditions": conditions,
        "test_ocr": {
            strategy: {
                "pooled": _ocr_entry(e3["ocr"][f"test/{strategy}"]["pooled"]),
                "by_condition": {
                    c: _ocr_entry(v)
                    for c, v in e3["ocr"][f"test/{strategy}"]["by_condition"].items()
                },
            }
            for strategy in ("P0_baseline", selection["preprocessing"])
        },
        "devval_preprocessing": {
            split: {
                key.split("/")[1]: {
                    **_ocr_entry(entry["pooled"]),
                    "delta_cer_vs_P0": e2["paired"]["preprocessing_vs_P0"]
                    .get(key, {})
                    .get("delta_cer"),
                }
                for key, entry in e2["ocr"].items()
                if key.startswith(f"{split}/")
            }
            for split in ("dev", "val")
        },
        "test_matching": {
            strategy: {
                m: _matching_entry(v)
                for m, v in e3["matching"][f"test/{strategy}"]["pooled"].items()
            }
            for strategy in ("P0_baseline", selection["preprocessing"])
        },
        "test_matching_delta_vs_M0": e3["paired"]["matchers_vs_M0"]["test/P0_baseline"],
        "tau_sweep": {
            "dev": summaries["e1_degradation"]["tau_sweep"]["dev/P0_baseline"],
            "test": e3["tau_sweep"]["test/P0_baseline"],
        },
        "matching_latency_us": e3["matching"]["test/P0_baseline"]["pooled"]["M0_baseline"][
            "match_latency_us_all_matchers"
        ],
    }
    path = root / EXPLORER_PATH
    path.write_text(
        json.dumps(explorer, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return path
