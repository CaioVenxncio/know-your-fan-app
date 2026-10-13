"""UI checks using Streamlit's headless AppTest runner."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from know_your_fan import app as app_module

MAIN = str(Path(__file__).resolve().parents[1] / "main.py")
FORBIDDEN_LABEL_WORDS = ("cpf", "rg", "cnh", "address", "password", "senha", "upload")


@pytest.fixture
def at(tmp_path, monkeypatch):
    monkeypatch.setenv("KYF_DB_PATH", str(tmp_path / "demo.db"))
    app_module.get_repository.clear()
    test = AppTest.from_file(MAIN, default_timeout=30)
    test.run()
    assert not test.exception
    return test


def goto(at, page):
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception


@pytest.mark.parametrize("page", app_module.PAGES)
def test_every_page_renders_without_sensitive_inputs(at, page):
    goto(at, page)
    labels = [w.label.casefold() for w in (*at.text_input, *at.text_area, *at.number_input)]
    for label in labels:
        assert not any(word in label.split() for word in FORBIDDEN_LABEL_WORDS), label
    # No password fields and no file uploader anywhere.
    assert all(getattr(w, "type", "default") != "password" for w in at.text_input)
    assert not at.get("file_uploader")
    assert any("synthetic" in w.value.casefold() for w in at.warning)


def test_explorer_lists_seeded_profiles(at):
    goto(at, "Fan explorer")
    assert any(f"of {app_module.SEED_DATASET_SIZE} fictional profiles" in c.value for c in at.caption)


def test_generator_adds_profile(at):
    goto(at, "Profile generator")
    at.number_input[0].set_value(42).run()
    at.button[0].click().run()
    at.button[1].click().run()
    assert any("added" in s.value for s in at.success)
    repo = app_module.get_repository()
    assert repo.count() == app_module.SEED_DATASET_SIZE + 1


def test_text_matching_page_states_disclaimer_and_handles_blank_name(at, monkeypatch):
    monkeypatch.setattr(app_module, "extract_text", lambda image: "Name: someone")
    goto(at, "Text-matching demo")
    assert any(app_module.MATCHING_DISCLAIMER == i.value for i in at.info)
    at.text_input[0].set_value("   ").run()
    at.button[0].click().run()
    assert not at.exception
    assert at.error, "blank name should produce a friendly error"
