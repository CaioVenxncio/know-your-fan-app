# ADR 0007: Research-informed matching rule (M1 adopted) and preprocessing (P0 kept)

- **Status:** Accepted (Phase 5)
- **Date:** 2026-10-13
- **Evidence:** the Phase 4 study ([report](../research/report.md), frozen record unchanged).

## Context

Phase 4 compared four matching rules and eight preprocessing strategies on synthetic cards, with
choices frozen on dev/val before one evaluation of a held-out test split. This ADR records which
results the **product** acts on.

**Research conclusions and product choices are kept separate.** The research reported what
happened on a synthetic benchmark. The decisions below are engineering choices for this
demonstration app, informed by that evidence and limited by it.

## Decision 1: the app matches names with M1 (token sequence on one line)

The app now accepts a name only if its **whole sequence of words** (order and repeats included)
appears on **one line** of the OCR text. Accent and case folding and whole-word tokens are
unchanged. M0, the original "every distinct word appears anywhere" rule, is kept unchanged as
`text_matching.match_name`. It is used for word-level feedback and as the research baseline.

Evidence, in the order it was available:

| Split | M0 FAR / FRR | M1 FAR / FRR | Note |
|---|---|---|---|
| Dev (E1, P0) | 0.57 % / 30.6 % | 0 % / 31.3 % | selection data |
| Val (E1, P0) | 0.94 % / 32.5 % | 0.05 % / 32.8 % | confirmation |
| Test (E3, P0) | 0.43 % [0, 1.0] / 34.6 % | 0 % [0, 0] / 34.9 % | pre-registered primary endpoint; ΔFRR(M1 − M0) +0.31 pp [+0.12, +0.55] |

- **Mechanism:** every M0 false accept on test came from names containing near-duplicate tokens
  (e.g. *Tânia Tainá*), where a decoy repeated a token that was already present. M0 ignores
  repetition and order, so it accepts these decoys; M1 does not. This is a property of the rule,
  independent of OCR.
- **Why not M2 or M3:**
  - Under the pre-registered 1 % FAR budget, M2's tolerance collapsed to M1 (τ = 0.05).
  - Larger tolerances traded FAR for FRR poorly.
  - M3 lowered FRR by 1.2 pp but accepted 2.5 % of near-miss decoys.
  - An arbitrary fuzzy threshold in the public app would be unjustified.
- **What M1's 0 % does not mean:** that real usage will have zero false accepts. It was measured
  on rule-generated decoys, one card template, and one engine.

## Decision 2: the app keeps P0 preprocessing (not the research-frozen P1)

The research froze P1 (no preprocessing) under a **CER** criterion, and its CER benefit held on
test. The app's question is different: **does the name match?** On the evidence available
without tuning on test, P1 shows no benefit for that question:

| P1 − P0 (paired, 95 % CI) | Dev | Val |
|---|---|---|
| ΔCER | −0.0143 [−0.0192, −0.0091] | −0.0128 [−0.0203, −0.0052] |
| ΔWER | −0.0055 | −0.0006 [−0.0055, +0.0050] |
| Δ name-token recall | +0.0040 [−0.0026, +0.0109] | +0.0045 [−0.0065, +0.0155] |
| M1 FRR | 0.332 vs 0.338 | 0.357 vs 0.351 (direction reverses) |

In addition:

- The pre-registered test result showed ΔWER and Δ name-token recall indistinguishable from 0. On
  the 7 conditions not used for selection, P1 was slightly *worse* (ΔCER +0.0028). The test split
  is cited here only as already-reported confirmation; it was not used to choose anything.
- P0 and P1 gave byte-identical transcripts on clean, rotated, and downscaled cards. The app's
  demo offers only blur and rotation.
- P1 is `convert("RGB")` with no EXIF handling. Adopting it would mean shipping an untested hybrid,
  because the product must keep EXIF transposition and its safety checks.

So the evidence is **insufficient** to change the product's preprocessing, and P0 stays. The
image validation (empty, oversized, and unsupported images), timeouts, rate limits, and
concurrency limits are unchanged.

## What changed and what did not

| Changed | Unchanged |
|---|---|
| App decision rule: M1 (`text_matching.match_name_sequence`) | M0 implementation (`match_name`), kept as baseline and for feedback |
| UI explains the "all words present, but not as this name" case | P0 preprocessing, EXIF handling, size limits, timeout |
| M1 code moved into `text_matching`; research M1 delegates to it | Frozen Phase 4 data, configurations, figures, report, and selections |

The refactor was verified by recomputing all 20,480 E3 trial decisions (M0, M1, M2 score, M3)
from the committed observations before and after: the outputs were identical (SHA-256
`712bcfdb…` both times).

## Regression tests

- `tests/unit/test_text_matching.py`:
  - the three Phase 4 names behind every M0 false accept (M0 accepts, M1 rejects);
  - order and single-line requirements;
  - whole words, accent and case folding;
  - compound names with particles;
  - verdict categories;
  - input validation.
- `tests/integration/test_app.py`: the UI rejects a scrambled-order transcript ("every word
  appears somewhere") and accepts the true sequence.
- `tests/unit/test_ocr.py`: the app's OCR path still applies P0 (`ocr.preprocess`) before
  `ocr.recognize`.
- `tests/unit/test_research_matching.py` (unchanged): research M1 behaviour, now through the
  shared implementation.
