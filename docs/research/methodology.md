# Methodology and pre-registration

**Status:** pre-registered. This document was committed **before** the main experiments (E1, E2, E3)
were run. Changes after that point are listed under [Deviations](#9-deviations-log) with reasons.
The Git history is the record.

**Scope:** a controlled study of OCR transcription and name matching on **synthetic** specimen
cards rendered by this project. No real people, documents, or identifiers are used. Nothing here
measures, or claims to measure, identity verification, document authentication, or fraud
detection.

## 1. Research question

> How do controlled image degradations and text-matching strategies affect the reliability, error
> rates, and computational cost of OCR-based name matching on synthetic document specimens?

The study keeps four levels separate:

| Level | Question | Measured by |
|---|---|---|
| OCR transcription | How close is the OCR text to the card's text? | CER, WER, exact-transcription rate |
| Name extraction / token recognition | Are the name tokens recovered from the "Name:" line? | Name-token precision, recall, F1 |
| Name matching | Does a matching rule accept the true name and reject other names? | FAR, FRR, precision, recall, F1 |
| Identity verification | *Out of scope.* | — |

## 2. Research questions and hypotheses

**Disclosure.** A cost pilot (`experiments/configs/pilot.toml`) ran before these hypotheses were
written: 6 **dev** sources × 16 conditions × 8 preprocessing strategies (768 OCR runs; commit
`fbc007d`). Its accuracy numbers were computed and seen. In particular, its pooled CER was lower
for 2× upscaling and higher for median filtering and Otsu thresholding than for the baseline, and
±8° rotation, σ=3 blur, 0.30× resolution, and the moderate combination caused very high CER. The
hypotheses below that state a direction for P3, P4, and P5 are therefore **informed by the pilot**
and are not independent confirmations. The confirmatory evidence is whether effects selected on
dev hold on val and on the held-out test split (RQ5). The test split was not used in the pilot.

| ID | Research question | Hypothesis (pre-registered) | Supported if |
|---|---|---|---|
| **H1a** | RQ1 degradation | Under the baseline pipeline, CER does not decrease as blur (σ 1→2→3) or resolution reduction (0.60→0.45→0.30) becomes more severe. | Point estimates are non-decreasing with severity on the test split. |
| **H1b** | RQ1 | Gaussian noise up to σ=40 has a small effect: CER increase ≤ 0.02 absolute versus clean. | Test-split CER(noise_40) − CER(clean) ≤ 0.02. |
| **H1c** | RQ1 | Rotation of 8° (either direction) increases CER more than 3° rotation. | CER(rot_±8) > CER(rot_±3) on test. |
| **H2a** | RQ2 preprocessing | P5 (2× upscaling) lowers CER versus P0 on resolution-reduced conditions. | Paired ΔCER(P5 − P0) 95% CI < 0 on test for res_0.45 and res_0.30 pooled. |
| **H2b** | RQ2 | P4 (median filter) raises pooled CER versus P0. | Paired ΔCER(P4 − P0) CI > 0 on dev and val. |
| **H2c** | RQ2 | P6 (inversion, as in the original 2025 app) does not improve CER versus P0. | ΔCER(P6 − P0) CI includes 0 or lies above 0 on dev and val. |
| **H2d** | RQ2 | Removing autocontrast or all preprocessing (P2, P1) changes pooled CER by less than 0.01 absolute. | \|ΔCER\| < 0.01 on dev and val. |
| **H3a** | RQ3 matching | M1 (token sequence) has FRR ≥ M0 and FAR ≤ M0. | Point estimates on test (P0). |
| **H3b** | RQ3 | M2 (tolerant, selected τ) has lower FRR than M0. | Paired ΔFRR(M2 − M0) CI < 0 on test (P0). |
| **H3c** | RQ3 | M2's extra tolerance raises FAR on near-miss negatives above M0's. | FAR_near-miss(M2) > FAR_near-miss(M0) on test. |
| **H3d** | RQ3 | M3 (confusable-aware) lowers FRR versus M1 without exceeding M2's near-miss FAR. | FRR(M3) < FRR(M1) and FAR_near-miss(M3) ≤ FAR_near-miss(M2) on test. |
| **H4a** | RQ4 cost | P5 increases median preprocessing + OCR latency by ≥ 20 % versus P0. | Median latency ratio on dev (E2). |
| **H4b** | RQ4 | Matching cost is negligible: the median time for all four matchers on one trial is < 1 ms, at least 100 times below median OCR latency. | Measured medians (test). |
| **H5a** | RQ5 robustness | The preprocessing strategy selected on dev also lowers pooled CER versus P0 on val and on test. | Paired ΔCER CI < 0 on val and on test. |
| **H5b** | RQ5 | The τ selected on dev keeps test FAR ≤ 2 % (target 1 %). | Test FAR(M2) point estimate ≤ 0.02. |

A hypothesis that is not supported is reported as such. Hypotheses will not be rewritten after
the results are seen.

## 3. Synthetic dataset

- **Version** `kyf-synth-names-v1`, **seed** `20261013`, **sizes** dev 80, val 80, test 160
  sources (`research/dataset.py`).
- **Names:** 32 given-name clusters and 30 surname clusters; a cluster groups near-duplicates
  (e.g. *Ivo/Ivan*, *Pereira/Ferreira*, *Iara/Lara*). Patterns, weighted:
  - Given Surname (25 %);
  - Given Surname Surname (30 %);
  - Given particle Surname Surname (15 %);
  - Given Given Surname Surname (15 %);
  - Given Surname Surname with the same surname twice (15 %).

  The names include short and long tokens, diacritics (á â ã é ê í ó ô õ ú ç), and names 1–2
  characters apart.
- **Splits without leakage:** whole clusters are assigned to one split, round-robin within token
  categories (accent / long / short / other). Dev, val, and test share **no given name or surname
  token**; only the particles *da, de, do, dos, das* are common to all splits. Names are unique.
  Every source in a split is a distinct name, so no rendered card is identical across splits.
  All cards share one layout (a limitation; see §8).
- **No collisions with card text:** no vocabulary token equals, after accent folding, any token of
  the fixed card text, the fictional cities, or the game titles. Demo IDs never contain a
  vocabulary token.
- **Ground truth:** `ocr.specimen_lines(profile)`, the exact strings drawn on the card.
- **Trials:** per source, one **positive** (the true name) and three **negatives**:
  - *easy*: another name of the same split sharing no token and no near-duplicate partner;
  - *token_swap*: one token replaced by an unrelated token of the same role and split;
  - *near_miss*: one token replaced by its cluster partner, or (for tokens without a partner) one
    letter replaced by a look-alike.

  Negatives whose accent-folded tokens equal the true name's would be ambiguous: they are
  resampled, and excluded and counted if no alternative exists. Positives:negatives = 1:3. Every
  matching strategy is scored on exactly the same trials.
- **Manifests:** `experiments/manifests/kyf-synth-names-v1-seed20261013/{sources,trials}.csv`.
  Images are regenerated deterministically and are not stored.

## 4. Experimental matrix

All experiments use real Tesseract with the application's engine settings (`ocr.recognize`:
`lang=por+eng`, 15 s timeout, default page segmentation). The environment is recorded per run.

| ID | Splits | Conditions | Preprocessing | OCR runs | Purpose |
|---|---|---|---|---|---|
| E1 | dev, val | all 16 | P0 | 2,560 | RQ1 on dev/val; baseline; τ selection (dev); τ check (val) |
| E2 | dev, val | 9 (below) | all 8 | 11,520 | RQ2, RQ4; preprocessing selection (dev) and check (val) |
| E3 | test | all 16 | P0 + selected candidate | 5,120 | RQ1, RQ3, RQ5 confirmatory; final numbers |

**Computational budget (from the pilot).**
- The pilot ran 768 tasks in 146.3 s of wall time, with 3 workers and one Tesseract thread each,
  on a 6-logical-CPU Windows machine with Tesseract 5.4.0. That is about **0.19 s per task**.
  Median preprocessing + OCR time per image ranged from 481 ms (P0) to 642 ms (P5); there were no
  timeouts or failures.
- Projected wall time: E1 ≈ 8 min, E2 ≈ 40 min, E3 ≈ 17 min, about 65 min in total.
- Projected committed data: about 0.7 MB of gzip observations, since the pilot compressed
  216 KB to 29 KB.
- Budget ceiling: 1.5 h of wall time and 10 MB of committed results.
- Sizes (dev 80, val 80, test 160 sources) were chosen to fit this budget while giving the test
  split twice the sources of each tuning split. They will not be reduced after seeing results.

**Degradation conditions:**

| Family | Conditions |
|---|---|
| Clean | clean |
| Gaussian blur σ | 1, 2, 3 |
| Rotation | −3°, +3°, −8°, +8° (bicubic, white fill, canvas expanded) |
| Additive Gaussian noise σ (0–255 scale) | 10, 25, 40 |
| Resolution scale | 0.60, 0.45, 0.30 (Lanczos) |
| Combined (blur, rotation, noise, scale) | combo_mild (1, +3°, 10, 0.60); combo_moderate (2, −8°, 25, 0.45) |

Order of operations: rotate, then blur, then downscale, then noise. Noise is seeded per (dataset
seed, source, condition). This one-factor-at-a-time design with two combinations isolates each
factor's effect, avoids a 4×4×4×4 Cartesian product, and still checks interaction realism.

**E2 condition subset (9 of 16):** clean, blur_2, blur_3, rot_+3, rot_−8, noise_40, res_0.45,
res_0.30, combo_mild. It covers every family at a moderate and/or severe level (where
preprocessing could help or harm), plus clean (to detect harm). **Disclosure:** chosen after the
pilot; it was not chosen to favour any strategy.

**Preprocessing strategies** (`research/preprocessing.py`):

| ID | Strategy |
|---|---|
| P0 | The app's own (EXIF transpose, grayscale, autocontrast) |
| P1 | None |
| P2 | Grayscale only |
| P3 | P0 + Otsu threshold |
| P4 | P0 + 3×3 median filter |
| P5 | P0 + 2× Lanczos upscaling |
| P6 | P0 + inversion |
| P7 | P0 + 2× upscaling + Otsu |

Ablations: P1/P2 versus P0 isolate grayscale and autocontrast; P3–P6 each add one step; P7
combines two steps.

**Matching strategies** (`research/matching.py`):

| ID | Rule |
|---|---|
| M0 | The app's matcher: every distinct normalized token appears anywhere |
| M1 | The ordered token sequence, repeats included, appears contiguously on one OCR line |
| M2 | As M1, but each token may differ by a normalized Levenshtein distance ≤ τ |
| M3 | As M1, after a fixed look-alike table (`rn→m`, `vv→w`, `cl→d`, `0→o`, `1/|/!/i→l`, `5/$→s`) is applied to both sides |

The M3 table is generic and was fixed before any experiment. It deliberately does **not** include
`ç→g`, the one misread seen in Phase 2 CI, to avoid tuning on an observed failure.

## 5. Pre-registered selection rules (frozen before E3)

- **S1, preprocessing (dev, E2):** compute pooled micro CER over the 9 E2 conditions for each
  strategy.
  1. The candidate is the strategy with the lowest dev CER.
  2. Strategies within 0.002 of each other are tied; the tie goes to the lower median latency.
  3. If the candidate does not beat P0 by at least 0.002 on dev, P0 is kept.

  The candidate's val ΔCER(candidate − P0) is reported, with no re-selection on val. **Freeze:**
  the candidate if its val ΔCER point estimate is < 0, otherwise P0. E3 always runs P0 plus the
  dev candidate (or P0 plus the second-best strategy if P0 wins), so the test comparison is
  informative either way.
- **S2, M2 threshold (dev, E1, P0, all conditions, all negative kinds pooled):** the largest τ in
  {0, 0.05, …, 0.40} whose dev FAR ≤ 0.01. FAR and FRR at that τ are reported on val.
- The selections are written to `experiments/configs/frozen_selection.json` and committed **before**
  E3 runs. The test split is never used for any choice.

## 6. Metrics

Defined in `research/metrics.py`; zero denominators are reported as n/a.

- **CER / WER:** edit distance divided by reference length, after Unicode NFC normalization and
  whitespace collapsing; case and diacritics are preserved. **Micro** aggregation (sum of edits /
  sum of reference units) over all observations of a group. Per-sample values are kept for
  distributions. Reference: all text lines of the card.
- **Exact-transcription rate:** the share of observations with CER = 0.
- **Name-token P/R/F1:** the multiset of normalized tokens after the first "Name" label in the OCR
  output, compared with the true name tokens. Micro-aggregated. If nothing is extracted,
  precision is undefined (n/a) and recall is 0.
- **Matching:**
  - TP/FP/TN/FN over trials;
  - FAR = FP/(FP+TN), over negative trials;
  - FRR = FN/(TP+FN), over positive trials;
  - precision, recall, F1;
  - FAR per negative kind.
- **Latency:** milliseconds for preprocessing and for OCR (the subprocess call), wall-clock per
  task; matching time in microseconds for all four matchers per trial. Reported as median, p90,
  p95, and max.
- **Failures and timeouts** are kept as empty transcripts. They count fully toward CER and WER,
  and every matcher rejects them. Their counts are always reported.

## 7. Statistical analysis plan

- 95 % percentile intervals from a **source-level (cluster) bootstrap**, B = 2,000, seed
  `20261013`. Each resample draws sources with replacement and keeps all of a source's
  conditions, strategies, and trials together, so correlated variants are not treated as
  independent. Paired differences (strategy − P0, matcher − M0) use the same resampled sources
  for both arms.
- **Primary endpoints (test split, E3):**
  1. ΔCER(frozen preprocessing − P0), pooled over the 16 conditions;
  2. FAR and FRR of M0–M3 under P0, and ΔFRR and ΔFAR of M1–M3 versus M0.
- Everything else is secondary or exploratory. There are no p-values and no significance claims;
  intervals that exclude 0 are described as such. With many secondary intervals, some will exclude
  0 by chance; only the primary endpoints carry the main conclusions.
- Dev, val, and test results are reported separately and never pooled.

## 8. Known threats (addressed in the report)

- One card template, one font, one renderer: results are not expected to transfer to real
  documents, photographs, or other layouts.
- Degradations are synthetic, not calibrated to real capture.
- A single OCR engine, version, and model set (`tessdata_fast` 4.1.0) on one machine. Latency is
  machine-specific.
- The pilot was seen before the hypotheses were written (disclosed above).
- The name vocabulary is limited and Brazilian-Portuguese-flavoured. Negatives are constructed,
  not sampled from a real population.

## 9. Deviations log

| Date | Change | Reason |
|---|---|---|
| 2026-10-13 | Per-experiment `summary.json` files are no longer committed; they are regenerated with `run_research.py evaluate`. | They are derived from the committed observation archives and exceeded the repository's 500 KB file limit. This affects storage only, not the analysis. Re-evaluation reproduces every field except matching latency, which is re-measured. |
| 2026-10-13 | None to the design, rules, hypotheses, or sample sizes. | S1 and S2 were applied as written (see `experiments/configs/frozen_selection.json`). |
| 2026-10-13 (found after E3) | **Pre-registration inconsistency, not corrected:** H2a's criterion names the *test* split, but E3 by design runs only P0 and the frozen strategy (P1), so P5 was never run on test. H2a is reported as supported on dev/val only and not evaluable on test as worded. | Disclosed rather than repaired after seeing results. |
