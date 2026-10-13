"""Source-level (cluster) bootstrap confidence intervals.

Observations derived from the same synthetic source (its degraded variants,
preprocessing strategies, and matching trials) are correlated. Intervals are
therefore computed by resampling **sources** with replacement and recomputing
the micro-averaged ratio (sum of numerators / sum of denominators) on each
resample. Paired differences reuse the same resampled sources for both arms.
Percentile intervals; fixed seed; resamples where a denominator is zero are
dropped and counted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

DEFAULT_RESAMPLES = 2000
DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True, slots=True)
class Interval:
    estimate: float | None
    low: float | None
    high: float | None
    n_sources: int
    resamples_used: int

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "estimate": self.estimate,
            "ci_low": self.low,
            "ci_high": self.high,
            "n_sources": self.n_sources,
            "resamples_used": self.resamples_used,
        }


Ratios = Mapping[str, tuple[float, float]]  # source_id -> (numerator, denominator)


def _resample_indices(n: int, resamples: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, n, size=(resamples, n))


def _percentiles(values: np.ndarray, confidence: float) -> tuple[float | None, float | None, int]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None, None, 0
    alpha = (1.0 - confidence) / 2.0
    low, high = np.quantile(finite, [alpha, 1.0 - alpha])
    return float(low), float(high), int(finite.size)


def _arrays(data: Ratios, sources: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    numerators = np.array([data[s][0] for s in sources], dtype=float)
    denominators = np.array([data[s][1] for s in sources], dtype=float)
    return numerators, denominators


def bootstrap_ratio(
    data: Ratios,
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Interval:
    """Micro-averaged ratio with a source-level percentile bootstrap interval."""
    sources = sorted(data)
    if not sources:
        return Interval(None, None, None, 0, 0)
    num, den = _arrays(data, sources)
    estimate = float(num.sum() / den.sum()) if den.sum() else None
    idx = _resample_indices(len(sources), resamples, seed)
    with np.errstate(divide="ignore", invalid="ignore"):
        stats = num[idx].sum(axis=1) / den[idx].sum(axis=1)
    low, high, used = _percentiles(stats, confidence)
    return Interval(estimate, low, high, len(sources), used)


def bootstrap_paired_difference(
    first: Ratios,
    second: Ratios,
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Interval:
    """Interval for ratio(first) - ratio(second), resampling shared sources jointly."""
    sources = sorted(set(first) & set(second))
    if not sources:
        return Interval(None, None, None, 0, 0)
    num_a, den_a = _arrays(first, sources)
    num_b, den_b = _arrays(second, sources)
    estimate = (
        float(num_a.sum() / den_a.sum() - num_b.sum() / den_b.sum())
        if den_a.sum() and den_b.sum()
        else None
    )
    idx = _resample_indices(len(sources), resamples, seed)
    with np.errstate(divide="ignore", invalid="ignore"):
        diffs = num_a[idx].sum(axis=1) / den_a[idx].sum(axis=1) - num_b[idx].sum(axis=1) / den_b[
            idx
        ].sum(axis=1)
    low, high, used = _percentiles(diffs, confidence)
    return Interval(estimate, low, high, len(sources), used)
