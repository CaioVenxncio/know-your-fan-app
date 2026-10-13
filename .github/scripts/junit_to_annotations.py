"""Print GitHub Actions error annotations for failed tests in JUnit XML reports.

Usage: python junit_to_annotations.py report.xml [report.xml ...]

Annotations are visible on the workflow run summary, so failure details can be
reviewed without access to the raw job logs.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_MESSAGE = 3000


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(paths: list[str]) -> int:
    failures = 0
    for path in paths:
        if not Path(path).exists():
            continue
        root = ET.parse(path).getroot()  # noqa: S314 - trusted, locally generated file
        for case in root.iter("testcase"):
            for problem in (*case.findall("failure"), *case.findall("error")):
                failures += 1
                name = f"{case.get('classname', '')}::{case.get('name', '')}"
                detail = (problem.get("message") or "") + "\n" + (problem.text or "")
                print(f"::error title={_escape(name)}::{_escape(detail.strip()[:MAX_MESSAGE])}")
    print(f"{failures} failing test(s) reported", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
