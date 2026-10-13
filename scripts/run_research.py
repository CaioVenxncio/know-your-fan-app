"""Command-line entry point for the OCR research experiments.

Examples:
    uv run python scripts/run_research.py run --config experiments/configs/pilot.toml
    uv run python scripts/run_research.py evaluate --config experiments/configs/pilot.toml
    uv run python scripts/run_research.py report

``run`` executes (or resumes) the OCR tasks of one configuration and requires
Tesseract. ``evaluate`` computes metrics from stored observations without
running OCR. ``report`` regenerates tables and figures from evaluated results.
None of these commands run automatically: not at app start-up, not on every CI
push.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from know_your_fan.research import experiments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Know Your Fan OCR research runner")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run or resume the OCR tasks of a configuration")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument(
        "--environment",
        default="local",
        help="label recorded with the results, e.g. local-windows, docker, ci-ubuntu",
    )
    run.add_argument("--root", type=Path, default=experiments.REPO_ROOT)

    evaluate = commands.add_parser("evaluate", help="compute metrics from stored observations")
    evaluate.add_argument("--config", type=Path, required=True)
    evaluate.add_argument("--root", type=Path, default=experiments.REPO_ROOT)

    report = commands.add_parser("report", help="regenerate tables and figures")
    report.add_argument("--root", type=Path, default=experiments.REPO_ROOT)

    explorer = commands.add_parser(
        "export-explorer", help="write the app's interactive research data from the summaries"
    )
    explorer.add_argument("--root", type=Path, default=experiments.REPO_ROOT)

    args = parser.parse_args(argv)
    if args.command == "run":
        config = experiments.load_config(args.config)
        out = experiments.run_experiment(config, root=args.root, environment_label=args.environment)
        print(f"observations written to {out}")
        return 0
    if args.command == "evaluate":
        from know_your_fan.research import evaluation

        config = experiments.load_config(args.config)
        summary_path = evaluation.evaluate_experiment(config, root=args.root)
        print(f"summary written to {summary_path}")
        return 0
    from know_your_fan.research import reporting

    if args.command == "export-explorer":
        print(f"wrote {reporting.export_explorer(root=args.root)}")
        return 0
    written = reporting.build_report(root=args.root)
    print("\n".join(f"wrote {p}" for p in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
