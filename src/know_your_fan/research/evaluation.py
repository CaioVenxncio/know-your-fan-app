"""Metric computation and aggregation from stored observations (no OCR is run).

Outputs, in the experiment's results directory:

* ``observation_metrics.csv``: one row per OCR observation (per-sample CER/WER
  counts, name-token counts, status, latencies).
* ``trial_scores.csv.gz``: one row per (observation, trial) with every
  matcher's decision and the M2 score, so all matching metrics can be audited.
* ``summary.json``: aggregates with source-level bootstrap intervals.

Failed or timed-out OCR is kept as an empty transcript: it counts toward CER
and WER (all reference characters are errors) and every matcher rejects it.
"""

from __future__ import annotations

import csv
import gzip
import json
import statistics
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from know_your_fan.research import degradations, matching, metrics, stats
from know_your_fan.research.dataset import Dataset, Source, Trial, build_dataset
from know_your_fan.research.experiments import (
    REPO_ROOT,
    ExperimentConfig,
    read_observations,
    results_dir,
)

TAU_GRID = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40)
FAR_TARGET = 0.01  # pre-registered: largest tau whose dev FAR <= 1 %
BOOTSTRAP_SEED = 20261013
MATCHERS_FIXED = ("M0_baseline", "M1_token_sequence", "M3_confusable")
NEGATIVE_KINDS = ("easy", "token_swap", "near_miss")


@dataclass(frozen=True, slots=True)
class ObservationMetrics:
    task_id: str
    source_id: str
    split: str
    condition: str
    family: str
    strategy: str
    status: str
    char_edits: int
    char_ref: int
    word_edits: int
    word_ref: int
    exact: int
    name_tp: int
    name_extracted: int
    name_expected: int
    preprocess_ms: float
    ocr_ms: float


def observation_metrics(row: dict[str, str], source: Source) -> ObservationMetrics:
    reference = "\n".join(source.ground_truth())
    text = row["ocr_text"] if row["status"] == "ok" else ""
    chars = metrics.character_errors(reference, text)
    words = metrics.word_errors(reference, text)
    tokens = metrics.name_token_counts(source.name, text)
    return ObservationMetrics(
        task_id=row["task_id"],
        source_id=row["source_id"],
        split=row["split"],
        condition=row["condition"],
        family=degradations.CONDITIONS[row["condition"]].family,
        strategy=row["strategy"],
        status=row["status"],
        char_edits=chars.edits,
        char_ref=chars.reference_length,
        word_edits=words.edits,
        word_ref=words.reference_length,
        exact=int(chars.edits == 0),
        name_tp=tokens.true_positive,
        name_extracted=tokens.extracted,
        name_expected=tokens.expected,
        preprocess_ms=float(row["preprocess_ms"]),
        ocr_ms=float(row["ocr_ms"]),
    )


@dataclass(frozen=True, slots=True)
class TrialScore:
    task_id: str
    trial_id: str
    source_id: str
    split: str
    condition: str
    strategy: str
    kind: str
    positive: int
    m0: int
    m1: int
    m3: int
    m2_score: float
    match_us: float  # total time of all matchers for this trial, microseconds


def score_trials(row: dict[str, str], trials: Sequence[Trial]) -> list[TrialScore]:
    text = row["ocr_text"] if row["status"] == "ok" else ""
    scores = []
    for trial in trials:
        started = time.perf_counter()
        m0 = matching.m0_baseline(trial.candidate, text)
        m1 = matching.m1_token_sequence(trial.candidate, text)
        m3 = matching.m3_confusable(trial.candidate, text)
        m2 = matching.m2_score(trial.candidate, text)
        elapsed = (time.perf_counter() - started) * 1e6
        scores.append(
            TrialScore(
                row["task_id"], trial.trial_id, trial.source_id, trial.split,
                row["condition"], row["strategy"], trial.kind, int(trial.is_positive),
                int(m0), int(m1), int(m3), round(m2, 6), round(elapsed, 1),
            )
        )  # fmt: skip
    return scores


def decision(score: TrialScore, matcher: str, tau: float) -> bool:
    if matcher == "M0_baseline":
        return bool(score.m0)
    if matcher == "M1_token_sequence":
        return bool(score.m1)
    if matcher == "M3_confusable":
        return bool(score.m3)
    if matcher == "M2_tolerant":
        return score.m2_score <= tau
    raise ValueError(f"unknown matcher {matcher}")


# ---------------------------------------------------------------- aggregation helpers


def _per_source(
    items: Iterable[Any], numerator: Callable[[Any], float], denominator: Callable[[Any], float]
) -> dict[str, tuple[float, float]]:
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for item in items:
        sums[item.source_id][0] += numerator(item)
        sums[item.source_id][1] += denominator(item)
    return {k: (v[0], v[1]) for k, v in sums.items()}


def _ci(data: dict[str, tuple[float, float]], seed: int) -> dict[str, Any]:
    return stats.bootstrap_ratio(data, seed=seed).as_dict()


def _quantiles(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "p90": None, "p95": None, "max": None, "n": 0}
    ordered = sorted(values)

    def pick(q: float) -> float:
        return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]

    return {
        "median": round(statistics.median(ordered), 3),
        "p90": round(pick(0.90), 3),
        "p95": round(pick(0.95), 3),
        "max": round(ordered[-1], 3),
        "n": len(ordered),
    }


def ocr_summary(observations: Sequence[ObservationMetrics], seed: int) -> dict[str, Any]:
    return {
        "n_observations": len(observations),
        "n_sources": len({o.source_id for o in observations}),
        "status": {
            s: sum(o.status == s for o in observations) for s in ("ok", "timeout", "failed")
        },
        "cer": _ci(_per_source(observations, lambda o: o.char_edits, lambda o: o.char_ref), seed),
        "wer": _ci(_per_source(observations, lambda o: o.word_edits, lambda o: o.word_ref), seed),
        "exact_rate": _ci(_per_source(observations, lambda o: o.exact, lambda o: 1), seed),
        "name_token_precision": metrics.ratio(
            sum(o.name_tp for o in observations), sum(o.name_extracted for o in observations)
        ),
        "name_token_recall": _ci(
            _per_source(observations, lambda o: o.name_tp, lambda o: o.name_expected), seed
        ),
        "name_token_f1": metrics.f1_from_counts(
            sum(o.name_tp for o in observations),
            sum(o.name_extracted for o in observations),
            sum(o.name_expected for o in observations),
        ),
        "latency_ms": {
            "preprocess": _quantiles([o.preprocess_ms for o in observations]),
            "ocr": _quantiles([o.ocr_ms for o in observations]),
            "preprocess_plus_ocr": _quantiles([o.preprocess_ms + o.ocr_ms for o in observations]),
        },
    }


def matching_summary(
    scores: Sequence[TrialScore], matcher: str, tau: float, seed: int
) -> dict[str, Any]:
    confusion = metrics.Confusion()
    for score in scores:
        confusion = confusion.add(
            actual=bool(score.positive), predicted=decision(score, matcher, tau)
        )
    negatives = [s for s in scores if not s.positive]
    positives = [s for s in scores if s.positive]
    per_kind = {}
    for kind in NEGATIVE_KINDS:
        subset = [s for s in negatives if s.kind == kind]
        per_kind[kind] = {
            "n": len(subset),
            "false_accepts": sum(decision(s, matcher, tau) for s in subset),
            "far": metrics.ratio(sum(decision(s, matcher, tau) for s in subset), len(subset)),
        }
    return {
        "tau": tau if matcher == "M2_tolerant" else None,
        "tp": confusion.tp,
        "fp": confusion.fp,
        "tn": confusion.tn,
        "fn": confusion.fn,
        "far": _ci(_per_source(negatives, lambda s: decision(s, matcher, tau), lambda s: 1), seed),
        "frr": _ci(
            _per_source(positives, lambda s: not decision(s, matcher, tau), lambda s: 1), seed
        ),
        "precision": confusion.precision,
        "recall": confusion.recall,
        "f1": confusion.f1,
        "far_by_negative_kind": per_kind,
        "match_latency_us_all_matchers": _quantiles([s.match_us for s in scores]),
    }


def _without_latency(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "match_latency_us_all_matchers"}


def tau_sweep(scores: Sequence[TrialScore]) -> list[dict[str, Any]]:
    rows = []
    positives = [s for s in scores if s.positive]
    negatives = [s for s in scores if not s.positive]
    for tau in TAU_GRID:
        rows.append(
            {
                "tau": tau,
                "far": metrics.ratio(sum(s.m2_score <= tau for s in negatives), len(negatives)),
                "frr": metrics.ratio(sum(s.m2_score > tau for s in positives), len(positives)),
                "n_negatives": len(negatives),
                "n_positives": len(positives),
            }
        )
    return rows


def select_tau(sweep: Sequence[dict[str, Any]], far_target: float = FAR_TARGET) -> float:
    """Pre-registered rule: the largest tau whose FAR is at most ``far_target``."""
    eligible = [r["tau"] for r in sweep if r["far"] is not None and r["far"] <= far_target]
    return max(eligible) if eligible else 0.0


def paired_difference(
    first: Sequence[Any],
    second: Sequence[Any],
    numerator: Callable[[Any], float],
    denominator: Callable[[Any], float],
    seed: int,
) -> dict[str, Any]:
    return stats.bootstrap_paired_difference(
        _per_source(first, numerator, denominator),
        _per_source(second, numerator, denominator),
        seed=seed,
    ).as_dict()


# ---------------------------------------------------------------- I/O


def _write_rows(handle: Any, rows: Iterable[Any], fields: Sequence[str]) -> None:
    writer = csv.writer(handle)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([getattr(row, f) for f in fields])


def _write_csv(path: Path, rows: Iterable[Any], fields: Sequence[str], compress: bool) -> None:
    if compress:
        with gzip.open(path, "wt", newline="", encoding="utf-8") as packed:
            _write_rows(packed, rows, fields)
    else:
        with path.open("w", newline="", encoding="utf-8") as plain:
            _write_rows(plain, rows, fields)


def load_observation_rows(directory: Path) -> list[dict[str, str]]:
    plain = directory / "observations.csv"
    if plain.exists():
        return read_observations(plain)
    packed = directory / "observations.csv.gz"
    if packed.exists():
        with gzip.open(packed, "rt", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    raise FileNotFoundError(f"no observations in {directory}")


def compute(
    dataset: Dataset, rows: Sequence[dict[str, str]]
) -> tuple[list[ObservationMetrics], list[TrialScore]]:
    sources = {s.source_id: s for s in dataset.sources}
    trials_by_source: dict[str, list[Trial]] = defaultdict(list)
    for trial in dataset.trials:
        trials_by_source[trial.source_id].append(trial)
    observations = [observation_metrics(r, sources[r["source_id"]]) for r in rows]
    scores = [s for r in rows for s in score_trials(r, trials_by_source[r["source_id"]])]
    return observations, scores


def _group(items: Iterable[Any], *keys: str) -> dict[tuple[str, ...], list[Any]]:
    groups: dict[tuple[str, ...], list[Any]] = defaultdict(list)
    for item in items:
        groups[tuple(getattr(item, k) for k in keys)].append(item)
    return dict(sorted(groups.items()))


def summarize(
    observations: Sequence[ObservationMetrics],
    scores: Sequence[TrialScore],
    *,
    tau: float,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """All aggregates for one experiment, at M2 threshold ``tau``."""
    matchers = (*MATCHERS_FIXED, "M2_tolerant")
    summary: dict[str, Any] = {"tau": tau, "ocr": {}, "matching": {}, "tau_sweep": {}}
    for (split, strategy), group in _group(observations, "split", "strategy").items():
        key = f"{split}/{strategy}"
        summary["ocr"][key] = {
            "pooled": ocr_summary(group, seed),
            "by_condition": {
                c: ocr_summary(g, seed) for (c,), g in _group(group, "condition").items()
            },
            "by_family": {f: ocr_summary(g, seed) for (f,), g in _group(group, "family").items()},
        }
    for (split, strategy), group in _group(scores, "split", "strategy").items():
        key = f"{split}/{strategy}"
        summary["matching"][key] = {
            "pooled": {m: matching_summary(group, m, tau, seed) for m in matchers},
            "by_condition": {
                c: {m: _without_latency(matching_summary(g, m, tau, seed)) for m in matchers}
                for (c,), g in _group(group, "condition").items()
            },
        }
        summary["tau_sweep"][key] = tau_sweep(group)
    summary["paired"] = paired_comparisons(observations, scores, tau=tau, seed=seed)
    return summary


def _accepted(score: TrialScore, *, matcher: str, tau: float) -> float:
    return float(decision(score, matcher, tau))


def _rejected(score: TrialScore, *, matcher: str, tau: float) -> float:
    return 1.0 - _accepted(score, matcher=matcher, tau=tau)


def _one(_: object) -> float:
    return 1.0


def paired_comparisons(
    observations: Sequence[ObservationMetrics],
    scores: Sequence[TrialScore],
    *,
    tau: float,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Paired differences on identical sources and trials (source-level bootstrap).

    * Preprocessing: strategy minus P0_baseline, per split, pooled over the
      conditions both arms share.
    * Matching: matcher minus M0_baseline, per split and strategy, on the same trials.
    """
    result: dict[str, Any] = {"preprocessing_vs_P0": {}, "matchers_vs_M0": {}}
    by_split = _group(observations, "split")
    for (split,), group in by_split.items():
        baseline = [o for o in group if o.strategy == "P0_baseline"]
        if not baseline:
            continue
        keys = {(o.source_id, o.condition) for o in baseline}
        for strategy in sorted({o.strategy for o in group} - {"P0_baseline"}):
            arm = [o for o in group if o.strategy == strategy]
            shared = keys & {(o.source_id, o.condition) for o in arm}
            a = [o for o in arm if (o.source_id, o.condition) in shared]
            b = [o for o in baseline if (o.source_id, o.condition) in shared]
            result["preprocessing_vs_P0"][f"{split}/{strategy}"] = {
                "n_pairs": len(shared),
                "delta_cer": paired_difference(
                    a, b, lambda o: o.char_edits, lambda o: o.char_ref, seed
                ),
                "delta_wer": paired_difference(
                    a, b, lambda o: o.word_edits, lambda o: o.word_ref, seed
                ),
                "delta_name_token_recall": paired_difference(
                    a, b, lambda o: o.name_tp, lambda o: o.name_expected, seed
                ),
            }
    for (split, strategy), group in _group(scores, "split", "strategy").items():
        negatives = [s for s in group if not s.positive]
        positives = [s for s in group if s.positive]
        baseline_accept = partial(_accepted, matcher="M0_baseline", tau=tau)
        baseline_reject = partial(_rejected, matcher="M0_baseline", tau=tau)
        entry: dict[str, Any] = {}
        for matcher in ("M1_token_sequence", "M2_tolerant", "M3_confusable"):
            accept = partial(_accepted, matcher=matcher, tau=tau)
            reject = partial(_rejected, matcher=matcher, tau=tau)
            entry[matcher] = {
                "delta_far": stats.bootstrap_paired_difference(
                    _per_source(negatives, accept, _one),
                    _per_source(negatives, baseline_accept, _one),
                    seed=seed,
                ).as_dict(),
                "delta_frr": stats.bootstrap_paired_difference(
                    _per_source(positives, reject, _one),
                    _per_source(positives, baseline_reject, _one),
                    seed=seed,
                ).as_dict(),
            }
        result["matchers_vs_M0"][f"{split}/{strategy}"] = entry
    return result


def evaluate_experiment(
    config: ExperimentConfig, *, root: Path = REPO_ROOT, tau: float | None = None
) -> Path:
    """Compute and write metrics for one experiment. Returns the summary path."""
    directory = results_dir(root, config.experiment_id)
    rows = load_observation_rows(directory)
    dataset = build_dataset(config.dataset)
    observations, scores = compute(dataset, rows)
    _write_csv(
        directory / "observation_metrics.csv",
        observations,
        list(ObservationMetrics.__dataclass_fields__),
        compress=False,
    )
    _write_csv(
        directory / "trial_scores.csv.gz",
        scores,
        list(TrialScore.__dataclass_fields__),
        compress=True,
    )
    chosen = tau if tau is not None else _frozen_tau(root)
    summary = summarize(observations, scores, tau=chosen)
    summary["experiment_id"] = config.experiment_id
    summary["dataset_fingerprint"] = dataset.fingerprint()
    path = directory / "summary.json"
    path.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


FROZEN_SELECTION = Path("experiments") / "configs" / "frozen_selection.json"


def _frozen_tau(root: Path) -> float:
    """The frozen M2 threshold if selection has happened; otherwise the M1-equivalent 0.0."""
    path = root / FROZEN_SELECTION
    if path.exists():
        return float(json.loads(path.read_text(encoding="utf-8"))["m2_tau"])
    return 0.0
