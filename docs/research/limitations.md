# Limitations and threats to validity

This page lists what the Phase 4 study can and cannot show. The [report](report.md) discusses how
each limitation affects specific findings.

## What the study is not

- **Not identity verification.** A matcher that accepts a name only says that those words were
  recognized in OCR output from a card this application drew itself. It says nothing about who
  holds a document, whether a document is genuine, or whether it was altered.
- **Not a real-document benchmark.** No real documents, photographs, people, or identifiers were
  used. Synthetic results are not evidence of performance on real cards, IDs, or photos.
- **Not peer-reviewed.** This is an independent portfolio study with a public, reproducible
  pipeline.

## Construct validity

- **One template, one font, one renderer.** Every card has the same layout, font (Aileron
  Regular), size, and colours. Real documents vary widely in all of these.
- **Simulated degradations.** Gaussian blur, rotation with white fill, additive Gaussian noise,
  and Lanczos downscaling are simple models. They omit perspective distortion, uneven lighting,
  glare, compression artefacts, motion blur, and physical wear.
- **Constructed negatives.** Decoy names come from fixed rules (unrelated name, one-token swap,
  near-duplicate or look-alike edit), not from a real population. FAR therefore depends on how
  hard these decoys are, and would differ for other decoy distributions.
- **Name-token metrics depend on the "Name:" label** being recognized. If OCR garbles the label,
  name extraction fails even when the name itself was read.

## Internal validity

- **Pilot exposure.** A 6-source dev pilot was seen before the hypotheses were written
  (disclosed in [methodology.md](methodology.md)). Directional hypotheses about preprocessing were
  informed by it.
- **Selection on dev, confirmation on held-out data.** Choices were frozen before the test split
  was evaluated. The E2 condition subset was chosen after the pilot.
- **Correlated observations.** Variants of one card are correlated. All intervals resample whole
  cards (a source-level bootstrap), but cards also share vocabulary within a split.

## External validity and reproducibility

- **One engine, one model set, one machine.** Tesseract 5.4.0 (UB Mannheim build) with
  `tessdata_fast` 4.1.0 `eng`/`por` models, on Windows with 6 logical CPUs. Other versions and
  models (for example `tessdata_best`, or the Ubuntu 5.3.4 package used in CI) can transcribe
  differently; a Phase 2 CI run already showed one such difference ("ç" read as "g").
- **Latency is machine-specific** and was measured with 3 parallel workers. Treat absolute times
  as illustrative; ratios between strategies are more transferable.
- **Vocabulary.** The 120 or so name tokens have a Brazilian-Portuguese flavour. Results for
  other scripts, languages, or name structures are unknown.

## Statistical limitations

- 95 % intervals are percentile bootstrap intervals over cards (B = 2,000). They describe
  sampling variability across synthetic cards drawn from this generator, not uncertainty about
  real-world performance.
- Many secondary comparisons are reported without multiplicity correction. Only the
  pre-registered primary endpoints support the main conclusions.
