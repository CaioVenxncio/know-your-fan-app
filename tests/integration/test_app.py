"""End-to-end UI checks using Streamlit's headless AppTest runner."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from know_your_fan import app as app_module
from know_your_fan import ocr, services
from know_your_fan.config import DB_PATH_ENV
from know_your_fan.storage import StorageError, StorageLimitError, SyntheticProfileRepository

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
    app_module.get_runtime.clear()
    test = AppTest.from_file(MAIN, default_timeout=30)
    test.run()
    assert not test.exception
    yield test
    app_module.get_runtime.clear()


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
    assert app_module.get_runtime().repository.count() == services.SEED_DATASET_SIZE + 1


def test_text_matching_success_path(at: AppTest, monkeypatch: pytest.MonkeyPatch) -> None:
    goto(at, "Text-matching demo")
    name = at.text_input[0].value
    monkeypatch.setattr(ocr, "extract_text", lambda image, **_: f"Name: {name}")
    at.button[0].click().run()
    assert any("All words of the name were found" in s.value for s in at.success)
    assert any(i.value == app_module.MATCHING_DISCLAIMER for i in at.info)


def test_text_matching_blank_name_shows_friendly_error(
    at: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "extract_text", lambda image, **_: "Name: someone")
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
    def failing(image: Image.Image, **_: object) -> str:
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
    app_module.get_runtime.clear()
    test = AppTest.from_file(MAIN, default_timeout=30)
    test.run()
    assert not test.exception
    assert any("demo dataset is unavailable" in e.value for e in test.error)
    app_module.get_runtime.clear()


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
    monkeypatch.setattr(ocr, "extract_text", lambda image, **_: text)
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


# ------------------------------------------------------------------ Phase 3: limits in the UI


@pytest.fixture
def make_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[dict[str, str]], AppTest]]:
    """Start the real app with extra environment variables (fresh process-wide runtime)."""
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "demo.db"))

    def start(env: dict[str, str]) -> AppTest:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        app_module.get_runtime.clear()
        test = AppTest.from_file(MAIN, default_timeout=30)
        test.run()
        assert not test.exception
        return test

    yield start
    app_module.get_runtime.clear()


def test_ocr_rate_limit_is_enforced_in_the_ui(
    make_app: Callable[[dict[str, str]], AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def counting_extract(image: Image.Image, **_: object) -> str:
        calls.append(1)
        return "Name: nobody"

    monkeypatch.setattr(ocr, "extract_text", counting_extract)
    at = make_app({"KYF_OCR_SESSION_LIMIT": "2", "KYF_OCR_GLOBAL_LIMIT": "2"})
    goto(at, "Text-matching demo")
    for _ in range(3):
        at.button[0].click().run()
    assert not at.exception
    assert len(calls) == 2  # the third request never reached the OCR engine
    assert any("Too many requests" in w.value for w in at.warning)


def test_busy_ocr_engine_message(
    make_app: Callable[[dict[str, str]], AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "extract_text", lambda image, **_: "unused")
    at = make_app({"KYF_OCR_MAX_CONCURRENCY": "1"})
    guard = app_module.get_runtime().ocr_guard
    guard.concurrency.wait_seconds = 0
    guard.concurrency.acquire()  # another session is using the only OCR slot
    try:
        goto(at, "Text-matching demo")
        at.button[0].click().run()
    finally:
        guard.concurrency.release()
    assert not at.exception
    assert any("busy" in w.value for w in at.warning)


def test_invalid_configuration_fails_closed_with_generic_message(
    make_app: Callable[[dict[str, str]], AppTest],
) -> None:
    at = make_app({"KYF_OCR_MAX_CONCURRENCY": "1000"})
    assert any("misconfigured" in e.value for e in at.error)
    assert not at.sidebar.radio  # the app stopped before rendering any page
    assert "1000" not in all_text(at)


def test_storage_failure_while_rendering_a_page_is_handled(
    at: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_list(self: object) -> list[object]:
        raise StorageError("A demo database operation failed.")

    monkeypatch.setattr(SyntheticProfileRepository, "list_all", failing_list)
    goto(at, "Fan explorer")
    assert not at.exception
    assert any("temporarily unavailable" in e.value for e in at.error)


def test_ui_flows_do_not_log_names_or_ocr_text(
    at: AppTest, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ocr_output = "OCR-OUTPUT-SHOULD-NOT-BE-LOGGED"

    def timing_out(image: Image.Image, **_: object) -> str:
        raise ocr.OCRTimeoutError("OCR timed out.")

    with caplog.at_level(logging.DEBUG, logger="know_your_fan"):
        goto(at, "Text-matching demo")
        name = at.text_input[0].value
        assert name
        monkeypatch.setattr(ocr, "extract_text", lambda image, **_: ocr_output)
        at.button[0].click().run()
        monkeypatch.setattr(ocr, "extract_text", timing_out)
        at.text_input[0].set_value("Zeferino Typed Name").run()
        at.button[0].click().run()
    assert not at.exception
    for sensitive in (ocr_output, name, "Zeferino", "Typed Name"):
        assert sensitive not in caplog.text
