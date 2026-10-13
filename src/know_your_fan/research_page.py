"""Research page: an interactive view of the precomputed Phase 4 results.

Reads ``experiments/results/research_explorer.json`` (and the smaller
``research_summary.json``). Nothing is computed beyond filtering and
formatting; no OCR runs. Every chart has a data table alternative, sample
sizes, and units.
"""

from __future__ import annotations

from typing import Any

import altair as alt
import streamlit as st

from know_your_fan import ui
from know_your_fan.research import presentation

# Vertical legends fit narrow (phone) viewports.
LEGEND = alt.Legend(orient="bottom", direction="vertical")

METRICS = {
    "CER": ("cer", "CER (lower is better)"),
    "WER": ("wer", "WER (lower is better)"),
    "Name-token recall": ("name_token_recall", "Name-token recall (higher is better)"),
}
FAMILY_LABELS = {
    "all": "All conditions",
    "clean": "Clean",
    "blur": "Blur",
    "rotation": "Rotation",
    "noise": "Noise",
    "resolution": "Resolution",
    "combined": "Combined",
}
STRATEGY_LABELS = {
    "P0_baseline": "P0 app preprocessing",
    "P1_none": "P1 no preprocessing",
    "P2_gray": "P2 grayscale only",
    "P3_otsu": "P3 + Otsu threshold",
    "P4_median": "P4 + median filter",
    "P5_upscale2": "P5 + 2x upscale",
    "P6_invert": "P6 + inversion",
    "P7_upscale2_otsu": "P7 + upscale + Otsu",
}
MATCHER_LABELS = {
    "M0_baseline": "M0 original rule (words anywhere)",
    "M1_token_sequence": "M1 name sequence on one line (app default)",
    "M2_tolerant": "M2 edit-tolerant",
    "M3_confusable": "M3 look-alike tolerant",
}


@st.cache_data(show_spinner=False)
def research_data() -> dict[str, Any] | None:
    """Precomputed research results, parsed once per process (immutable asset)."""
    return presentation.load_explorer()


def _pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def _count(entry: dict[str, Any]) -> str:
    """False accepts as '33 of 7,680 (0.43%)' over all decoy trials."""
    total = entry["fp"] + entry["tn"]
    return f"{entry['fp']:,} of {total:,} ({_pct(entry['fp'] / total, 2)})"


def _interval_text(entry: dict[str, Any], digits: int = 3) -> str:
    if entry.get("estimate") is None:
        return "n/a"
    low, high = entry["ci_low"], entry["ci_high"]
    return f"{entry['estimate']:.{digits}f} [{low:.{digits}f}, {high:.{digits}f}]"


def _point_chart(
    rows: list[dict[str, Any]],
    category: str,
    category_title: str,
    color: str,
    color_title: str,
    value_title: str,
) -> alt.LayerChart | alt.FacetChart:
    """Horizontal dot plot with 95% interval bars: categories on the y axis stay readable."""
    categories = list(dict.fromkeys(r[category] for r in rows))
    base = alt.Chart({"values": rows}).encode(
        y=alt.Y(f"{category}:N", title=category_title, sort=categories,
                axis=alt.Axis(labelLimit=220)),
        yOffset=alt.YOffset(f"{color}:N"),
        color=alt.Color(f"{color}:N", title=color_title, legend=LEGEND),
    )  # fmt: skip
    tooltip = [
        alt.Tooltip(f"{category}:N", title=category_title),
        alt.Tooltip(f"{color}:N", title=color_title),
        alt.Tooltip("estimate:Q", title="Estimate", format=".4f"),
        alt.Tooltip("ci_low:Q", title="95% CI low", format=".4f"),
        alt.Tooltip("ci_high:Q", title="95% CI high", format=".4f"),
        alt.Tooltip("n_cards:Q", title="Cards (n)"),
    ]
    points = base.mark_point(filled=True, size=70).encode(
        x=alt.X("estimate:Q", title=value_title, scale=alt.Scale(domainMin=0)),
        shape=alt.Shape(f"{color}:N", title=color_title),
        tooltip=tooltip,
    )
    intervals = base.mark_rule(strokeWidth=2).encode(x="ci_low:Q", x2="ci_high:Q")
    return alt.layer(intervals, points, height=max(160, 34 * len(categories)))


def _rows_table(rows: list[dict[str, Any]], columns: dict[str, str]) -> None:
    st.dataframe(
        [{label: row[key] for key, label in columns.items()} for row in rows],
        hide_index=True,
        width="stretch",
    )


def page_research() -> None:
    ui.eyebrow("Phase 4 study · synthetic cards · pre-registered")
    st.header("How reliable is OCR name matching?")
    st.info(
        "Synthetic-data study. These numbers describe OCR text matching on fictional cards "
        "rendered by this app. They are not identity-verification, document-authentication, or "
        "fraud-detection performance and do not transfer to real documents."
    )
    explorer = research_data()
    if explorer is None:
        st.warning("No research results are available in this deployment.")
        return
    if explorer.get("status") == "final":
        st.success(
            "Final results: choices were frozen on dev/val before the single test-split run."
        )
    else:
        st.warning("Preliminary results: the held-out test evaluation is not complete.")

    runs = explorer["runs"]
    test_cards = explorer["test_ocr"]["P0_baseline"]["pooled"]["n_sources"]
    cols = st.columns(4)
    cols[0].metric("Real OCR runs", f"{presentation.total_ocr_runs(explorer):,}")
    cols[1].metric("Held-out test cards", f"{test_cards}")
    cols[2].metric("Degradation conditions", f"{runs['e3_test']['n_conditions']}")
    cols[3].metric("Matching rules compared", f"{len(explorer['test_matching']['P0_baseline'])}")

    st.subheader("The question")
    st.write(
        "How do image degradations, preprocessing, and the text-matching rule affect OCR "
        "transcription errors, name-matching error rates, and cost? Dev and val splits were used "
        "to choose settings; a held-out test split of fictional names never seen during selection "
        "was evaluated once."
    )

    clean = explorer["test_ocr"]["P0_baseline"]["by_condition"]["clean"]
    matching = explorer["test_matching"]["P0_baseline"]
    st.subheader("Key findings (test split)")
    st.write(
        f"- **Image quality dominates.** Clean cards: CER {clean['cer']['estimate']:.4f}, "
        f"{_pct(clean['exact_rate']['estimate'])} transcribed exactly. ±8° rotation, strong blur, "
        "and 0.30x resolution push CER to between 0.5 and 0.95.\n"
        f"- **Matching rules shift a small false-acceptance rate.** The original rule (M0) "
        f"accepted {_count(matching['M0_baseline'])} decoy names; the name-sequence rule "
        f"(M1, now the app default) accepted {_count(matching['M1_token_sequence'])}. "
        f"All rules rejected about {_pct(matching['M1_token_sequence']['frr']['estimate'], 0)} "
        "of true names, mostly on severely degraded cards.\n"
        "- **Error tolerance traded poorly.** Allowing edits raised false acceptances much faster "
        "than it lowered false rejections, so a 1% false-acceptance budget selected no tolerance.\n"
        "- **Preprocessing is condition-specific.** Median filtering and thresholding hurt; 2x "
        "upscaling helped low-resolution cards; dropping the app's own preprocessing lowered CER "
        "slightly but did not change name recognition."
    )

    tabs = st.tabs(["Degradations", "Preprocessing", "Matching", "Method & limits"])
    with tabs[0]:
        _degradations(explorer)
    with tabs[1]:
        _preprocessing(explorer)
    with tabs[2]:
        _matching(explorer)
    with tabs[3]:
        _method(explorer)


def _degradations(explorer: dict[str, Any]) -> None:
    n_cards = explorer["test_ocr"]["P0_baseline"]["pooled"]["n_sources"]
    st.caption(
        f"Test split, {n_cards} fictional cards per condition and strategy; "
        "95% bootstrap CIs; hover a point for exact values."
    )
    families = ["all", *dict.fromkeys(c["family"] for c in explorer["conditions"])]
    left, right = st.columns(2)
    family = left.selectbox(
        "Degradation family", families, format_func=lambda f: FAMILY_LABELS.get(f, f)
    )
    metric_label = right.radio("Metric", list(METRICS), horizontal=True, key="deg_metric")
    metric, title = METRICS[metric_label]
    rows = presentation.condition_rows(explorer, metric, None if family == "all" else family)
    for row in rows:
        row["strategy"] = STRATEGY_LABELS.get(row["strategy"], row["strategy"])
    st.altair_chart(
        _point_chart(rows, "condition", "Condition", "strategy", "Preprocessing", title),
        width="stretch",
    )
    with st.expander("Data table"):
        _rows_table(
            rows,
            {
                "condition": "Condition",
                "strategy": "Preprocessing",
                "estimate": metric_label,
                "ci_low": "95% CI low",
                "ci_high": "95% CI high",
                "n_cards": "Cards (n)",
            },
        )


def _preprocessing(explorer: dict[str, Any]) -> None:
    dev_cards = explorer["devval_preprocessing"]["dev"]["P0_baseline"]["n_sources"]
    n_conditions = explorer["runs"]["e2_preprocessing"]["n_conditions"]
    st.caption(
        f"Dev and val splits ({dev_cards} cards each), pooled over {n_conditions} conditions. "
        "Rule: lowest dev CER, confirmed on val. Frozen choice for the research: "
        f"{STRATEGY_LABELS.get(explorer['selection']['preprocessing'])}. The app keeps P0 (see "
        "the decision record)."
    )
    metric_label = st.radio("Metric", list(METRICS), horizontal=True, key="pre_metric")
    metric, title = METRICS[metric_label]
    rows = presentation.preprocessing_rows(explorer, metric)
    for row in rows:
        row["strategy"] = STRATEGY_LABELS.get(row["strategy"], row["strategy"])
    st.altair_chart(
        _point_chart(rows, "strategy", "Preprocessing", "split", "Split", title),
        width="stretch",
    )
    st.markdown("**Accuracy vs latency (dev)**")
    dev = [r for r in presentation.preprocessing_rows(explorer, "cer") if r["split"] == "dev"]
    for row in dev:
        row["strategy"] = STRATEGY_LABELS.get(row["strategy"], row["strategy"])
    scatter = (
        alt.Chart({"values": dev})
        .mark_point(filled=True, size=80)
        .encode(
            x=alt.X("median_latency_ms:Q", title="Median preprocessing + OCR time (ms)",
                    scale=alt.Scale(domainMin=0)),
            y=alt.Y("estimate:Q", title="CER (lower is better)", scale=alt.Scale(domainMin=0)),
            shape=alt.Shape("strategy:N", title="Preprocessing"),
            color=alt.Color(
                "strategy:N", title="Preprocessing", legend=LEGEND
            ),
            tooltip=[
                alt.Tooltip("strategy:N", title="Preprocessing"),
                alt.Tooltip("estimate:Q", title="CER", format=".4f"),
                alt.Tooltip("median_latency_ms:Q", title="Median ms", format=".0f"),
            ],
        )
        .properties(height=300)
    )  # fmt: skip
    st.altair_chart(scatter, width="stretch")
    with st.expander("Data table"):
        _rows_table(
            rows,
            {
                "split": "Split",
                "strategy": "Preprocessing",
                "estimate": metric_label,
                "ci_low": "95% CI low",
                "ci_high": "95% CI high",
                "median_latency_ms": "Median ms",
                "n_cards": "Cards (n)",
            },
        )


def _matching(explorer: dict[str, Any]) -> None:
    m0 = explorer["test_matching"]["P0_baseline"]["M0_baseline"]
    st.caption(
        f"Test split, app preprocessing (P0): {m0['tp'] + m0['fn']:,} true-name trials and "
        f"{m0['fp'] + m0['tn']:,} decoy trials. FAR = decoys accepted; "
        "FRR = true names rejected."
    )
    rows = []
    for matcher, entry in explorer["test_matching"]["P0_baseline"].items():
        kinds = entry["far_by_negative_kind"]
        rows.append(
            {
                "Rule": MATCHER_LABELS.get(matcher, matcher)
                + (f" (τ={entry['tau']:.2f})" if entry["tau"] is not None else ""),
                "FAR [95% CI]": _interval_text(entry["far"], 4),
                "FRR [95% CI]": _interval_text(entry["frr"]),
                "Decoys accepted (easy / swap / near-miss)": " / ".join(
                    f"{kinds[k]['false_accepts']}/{kinds[k]['n']}"
                    for k in ("easy", "token_swap", "near_miss")
                ),
                "TP / FP / TN / FN": " / ".join(str(entry[k]) for k in ("tp", "fp", "tn", "fn")),
            }
        )
    st.dataframe(rows, hide_index=True, width="stretch")
    st.markdown("**False acceptance vs false rejection as edit tolerance τ grows (rule M2)**")
    sweep = presentation.sweep_rows(explorer)
    chart = (
        alt.Chart({"values": sweep})
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=60))
        .encode(
            x=alt.X("far:Q", title="FAR (decoys accepted)",
                    axis=alt.Axis(format="%"), scale=alt.Scale(domainMin=0)),
            y=alt.Y("frr:Q", title="FRR (true names rejected)",
                    axis=alt.Axis(format="%"), scale=alt.Scale(domainMin=0)),
            color=alt.Color("split:N", title="Split", legend=LEGEND),
            strokeDash=alt.StrokeDash("split:N", title="Split"),
            order="tau:Q",
            tooltip=[
                alt.Tooltip("split:N", title="Split"),
                alt.Tooltip("tau:Q", title="τ", format=".2f"),
                alt.Tooltip("far:Q", title="FAR", format=".2%"),
                alt.Tooltip("frr:Q", title="FRR", format=".2%"),
                alt.Tooltip("n_negatives:Q", title="Decoy trials"),
                alt.Tooltip("n_positives:Q", title="True-name trials"),
            ],
        )
        .properties(height=320)
    )  # fmt: skip
    st.altair_chart(chart, width="stretch")
    with st.expander("Data table"):
        _rows_table(
            sweep,
            {
                "split": "Split",
                "tau": "τ",
                "far": "FAR",
                "frr": "FRR",
                "n_negatives": "Decoy trials",
                "n_positives": "True-name trials",
            },
        )


def _method(explorer: dict[str, Any]) -> None:
    runs = explorer["runs"]
    st.write(
        "- **Data:** fictional names in disjoint dev / val / test splits (no shared given name or "
        "surname); 1 true name and 3 decoys per card (unrelated, one word swapped, near "
        "duplicate).\n"
        "- **Conditions:** blur, rotation, noise, resolution, and two combinations; 8 "
        "preprocessing strategies; 4 matching rules; Tesseract "
        f"{runs['e3_test']['tesseract_version']}.\n"
        "- **Statistics:** 95% intervals from a card-level bootstrap (2,000 resamples).\n"
        "- **Process:** hypotheses and selection rules were committed before the experiments; "
        "several hypotheses were not supported and are reported as such."
    )
    st.write(
        "**Limitations.** One card template and font, simulated degradations, rule-generated "
        "decoys, one OCR engine on one machine. Results describe this synthetic benchmark only."
    )
    st.caption(
        f"Full report: {presentation.REPORT_PATH} in the repository "
        f"({presentation.REPOSITORY_URL})."
    )
