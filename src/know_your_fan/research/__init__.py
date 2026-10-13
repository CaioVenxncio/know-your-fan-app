"""Reproducible OCR research harness (Phase 4).

Separate from the Streamlit presentation layer. Modules:

* ``dataset``: deterministic synthetic names, sources, splits, and matching trials.
* ``degradations``: controlled, seeded image degradations.
* ``preprocessing``: preprocessing strategies (P0 is the application's own).
* ``matching``: name-matching strategies M0-M3.
* ``metrics``: CER, WER, name-token precision/recall/F1, confusion-matrix rates.
* ``stats``: source-level paired bootstrap confidence intervals.
* ``experiments``: configuration, task execution, provenance, results storage.
* ``evaluation`` / ``reporting``: metric aggregation, tables, and figures.

All data is synthetic. Nothing here performs identity verification.
"""
