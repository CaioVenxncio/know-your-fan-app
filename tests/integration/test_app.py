"""End-to-end UI checks using Streamlit's headless AppTest runner."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from know_your_fan import app as app_module
from know_your_fan import ocr, services
from know_your_fan.config import DB_PATH_ENV
from know_your_fan.storage import StorageLimitError, SyntheticProfileRepository

MAIN = str(Path(__file__).resolve().parents[2] / "main.py")
FORBIDDEN_INPUT_WORDS = ("cpf", "rg", "cnh", "address", "password", "senha", "upload")
MISLEADING_CLAIMS = (
    "documento válido",
    "document is valid",
    "valid document",
    "identity verified",
    "verified identity",
    "authentic document",
)


@pytest.fixture
def at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[AppTest]:
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "demo.db"))
    app_module.get_repository.clear()
    test = AppTest.from_file(MAIN, default_timeout=30)
    test.run()
    assert not test.exception
    yield test
    app_module.get_repository.clear()


def goto(at: AppTest, page: str) -> None:
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception


def all_text(at: AppTest) -> str:
    groups = (
        at.title, at.header, at.subheader, at.markdown, at.text, at.caption,
        at.info, at.success, at.warning, at.error, at.code,
    )  # fmt: skip
    return "\n".join(str(element.value) for group in groups for element in group).casefold()


@pytest.mark.parametrize("page", app_module.PAGES)
def test_pages_have_no_sensitive_inputs_or_claims(at: AppTest, page: str) -> None:
    goto(at, page)
    labels = [w.label.casefold() for w in (*at.text_input, *at.text_area, *at.number_input)]
    for label in labels:
        assert not any(word in label.split() for word in FORBIDDEN_INPUT_WORDS), label
    assert all(w.proto.type != w.proto.PASSWORD for w in at.text_input)
    assert not at.get("file_uploader")
    assert not at.get("camera_input")
    text = all_text(at)
    assert "synthetic" in text
    assert not any(claim in text for claim in MISLEADING_CLAIMS)


def test_explorer_lists_seeded_profiles_and_filters(at: AppTest) -> None:
    goto(at, "Fan explorer")
    total = services.SEED_DATASET_SIZE
    assert any(f"{total} of {total} fictional profiles" in c.value for c in at.caption)
    at.text_input[0].set_value("zzz-no-such-fan").run()
    assert any(f"0 of {total} fictional profiles" in c.value for c in at.caption)


def test_explorer_shows_details_as_plain_text(at: AppTest) -> None:
    goto(at, "Fan explorer")
    assert any(t.value.startswith("Demo ID: KYF-DEMO-") for t in at.text)


def test_generator_adds_profile_once(at: AppTest) -> None:
    goto(at, "Profile generator")
    at.number_input[0].set_value(42).run()
    at.button[0].click().run()
    at.button[1].click().run()
    assert any("added" in s.value for s in at.success)
    at.button[1].click().run()
    assert any("already" in i.value for i in at.info)
    assert app_module.get_repository().count() == services.SEED_DATASET_SIZE + 1


def test_text_matching_success_path(at: AppTest, monkeypatch: pytest.MonkeyPatch) -> None:
    goto(at, "Text-matching demo")
    name = at.text_input[0].value
    monkeypatch.setattr(ocr, "extract_text", lambda image: f"Name: {name}")
    at.button[0].click().run()
    assert any("All words of the name were found" in s.value for s in at.success)
    assert any(i.value == app_module.MATCHING_DISCLAIMER for i in at.info)


def test_text_matching_blank_name_shows_friendly_error(
    at: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "extract_text", lambda image: "Name: someone")
    goto(at, "Text-matching demo")
    at.text_input[0].set_value("   ").run()
    at.button[0].click().run()
    assert not at.exception
    assert any("at least one letter" in e.value for e in at.error)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ocr.OCRUnavailableError("not installed"), "OCR is unavailable"),
        (ocr.OCRFailedError("timed out"), "OCR failed"),
    ],
)
def test_text_matching_ocr_errors_are_friendly(
    at: AppTest, monkeypatch: pytest.MonkeyPatch, error: Exception, message: str
) -> None:
    def failing(image: Image.Image) -> str:
        raise error

    monkeypatch.setattr(ocr, "extract_text", failing)
    goto(at, "Text-matching demo")
    at.button[0].click().run()
    assert not at.exception
    assert any(message in e.value for e in at.error)


def test_unavailable_database_shows_error_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "is_a_dir.db"
    directory.mkdir()
    monkeypatch.setenv(DB_PATH_ENV, str(directory))
    app_module.get_repository.clear()
    test = AppTest.from_file(MAIN, default_timeout=30)
    test.run()
    assert not test.exception
    assert any("demo dataset is unavailable" in e.value for e in test.error)
    app_module.get_repository.clear()


@pytest.mark.parametrize(
    ("ocr_text", "expected_message"),
    [
        ("first-word-only", "Some words were found"),
        ("Unrelated text", "None of the words"),
    ],
)
def test_text_matching_partial_and_no_match_messages(
    at: AppTest, monkeypatch: pytest.MonkeyPatch, ocr_text: str, expected_message: str
) -> None:
    goto(at, "Text-matching demo")
    name = at.text_input[0].value
    assert name
    first_name = name.split()[0]
    text = ocr_text.replace("first-word-only", first_name)
    monkeypatch.setattr(ocr, "extract_text", lambda image: text)
    at.button[0].click().run()
    assert any(expected_message in w.value for w in at.warning)


def test_generator_reports_storage_limit(at: AppTest, monkeypatch: pytest.MonkeyPatch) -> None:
    def full(self: object, profile: object) -> bool:
        raise StorageLimitError("The demo dataset is limited to 500 profiles.")

    monkeypatch.setattr(SyntheticProfileRepository, "add", full)
    goto(at, "Profile generator")
    at.button[0].click().run()
    at.button[1].click().run()
    assert not at.exception
    assert any("limited to 500" in w.value for w in at.warning)
