"""Rendering-safety tests for the static HTML helpers."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from know_your_fan import ui

SRC = Path(ui.__file__).resolve().parent
PAYLOAD = '<img src=x onerror="alert(1)"><script>alert(1)</script>'


@pytest.fixture
def rendered(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake_markdown(body: str, *, unsafe_allow_html: bool = False) -> None:
        assert unsafe_allow_html
        calls.append(body)

    monkeypatch.setattr("know_your_fan.ui.st.markdown", fake_markdown)
    return calls


def test_helpers_escape_markup_in_text_arguments(rendered: list[str]) -> None:
    ui.eyebrow(PAYLOAD)
    ui.hero(PAYLOAD, PAYLOAD)
    ui.step(1, PAYLOAD)
    assert len(rendered) == 3
    for body in rendered:
        assert "<script>" not in body
        assert "<img" not in body
        assert "&lt;script&gt;" in body


def test_raw_html_is_only_emitted_by_the_ui_module() -> None:
    # Any other module passing unsafe_allow_html=True would bypass the static-string
    # policy documented in ui.py and app.py.
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "ui.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.keyword) and node.arg == "unsafe_allow_html":
                offenders.append(f"{path.relative_to(SRC)}:{node.value.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in {"html", "components"}:
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno} st.{node.attr}")
    assert offenders == []
