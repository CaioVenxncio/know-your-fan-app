"""End-to-end UI checks using Streamlit's headless AppTest runner."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button

from know_your_fan import app as app_module
from know_your_fan import ocr, research_page, services
from know_your_fan.config import DB_PATH_ENV
from know_your_fan.research import presentation
from know_your_fan.storage import StorageError, StorageLimitError, SyntheticProfileRepository

ROOT = Path(__file__).resolve().parents[2]
MAIN = str(ROOT / "main.py")
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
    """Switch to a section, as the sidebar navigation does (the page persists across reruns)."""
    script = app_module.page_script(page).relative_to(ROOT).as_posix()
    at.switch_page(script).run()
    assert not at.exception
    assert at.title, "every page has an h1"


def button(at: AppTest, label: str) -> Button:
    return next(b for b in at.button if b.label == label)


def all_text(at: AppTest) -> str:
    groups = (
        at.title, at.header, at.subheader, at.markdown, at.text, at.caption,
        at.info, at.success, at.warning, at.error, at.code,
    )  # fmt: skip
    return "\n".join(str(element.value) for group in groups for element in group).casefold()


# ------------------------------------------------------------------ privacy boundaries


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
    assert app_module.SYNTHETIC_NOTICE.casefold() in text  # notice on every page
    assert "synthetic data only" in text  # sidebar label
    assert not any(claim in text for claim in MISLEADING_CLAIMS)


# ------------------------------------------------------------------ navigation


def test_home_is_the_default_page_and_links_to_sections(at: AppTest) -> None:
    assert [t.value for t in at.title] == ["Know Your Fan"]
    assert "not identity verification" in all_text(at)
    labels = {b.label for b in at.button}
    assert set(app_module.HOME_ACTIONS.values()) <= labels
    button(at, app_module.HOME_ACTIONS["OCR demo"]).click().run()
    assert not at.exception
    assert [t.value for t in at.title] == ["OCR demo"]
    assert "Extract text and compare" in {b.label for b in at.button}


@pytest.mark.parametrize(
    ("page", "title"),
    [
        ("Fans", "Fans"),
        ("OCR demo", "OCR demo"),
        ("Research", "How reliable is OCR name matching?"),
    ],
)
def test_every_home_action_opens_its_page(at: AppTest, page: str, title: str) -> None:
    button(at, app_module.HOME_ACTIONS[page]).click().run()
    assert not at.exception
    assert [t.value for t in at.title] == [title]
    goto(at, page)  # and the navigation entry for the same section opens the same page
    assert [t.value for t in at.title] == [title]


def test_home_study_summary_uses_committed_results(at: AppTest) -> None:
    explorer = presentation.load_explorer()
    assert explorer is not None
    scope = presentation.study_scope(explorer)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics == {
        "Synthetic cards": f"{scope['cards']:,}",
        "OCR runs": f"{scope['ocr_runs']:,}",
        "Matching rules": f"{scope['matching_rules']}",
    }
    m0 = explorer["test_matching"]["P0_baseline"]["M0_baseline"]
    assert f"{m0['fp']} of {m0['fp'] + m0['tn']:,}" in all_text(at)


# ------------------------------------------------------------------ fans


def test_explorer_lists_seeded_profiles_and_filters(at: AppTest) -> None:
    goto(at, "Fans")
    total = services.SEED_DATASET_SIZE
    assert any(f"{total} of {total} profiles" in c.value for c in at.caption)
    search = next(t for t in at.text_input if t.label == "Search name or city")
    search.set_value("zzz-no-such-fan").run()
    assert any("No fictional fans match" in i.value for i in at.info)  # empty state
    assert not at.dataframe


def test_profile_card_renders_generated_values_as_plain_text(at: AppTest) -> None:
    goto(at, "Fans")
    profiles = app_module.get_runtime().repository.list_all()
    texts = {t.value for t in at.text}
    assert any(p.demo_id in texts for p in profiles)  # full ID, never truncated
    assert any(p.name in texts for p in profiles)


def test_generator_adds_profile_once(at: AppTest) -> None:
    goto(at, "Fans")
    at.number_input[0].set_value(42).run()
    button(at, "Generate profile").click().run()
    button(at, "Add to demo dataset").click().run()
    assert any("added" in s.value for s in at.success)
    button(at, "Add to demo dataset").click().run()
    assert any("already" in i.value for i in at.info)
    assert app_module.get_runtime().repository.count() == services.SEED_DATASET_SIZE + 1


def test_generator_reports_storage_limit(at: AppTest, monkeypatch: pytest.MonkeyPatch) -> None:
    def full(self: object, profile: object) -> bool:
        raise StorageLimitError("The demo dataset is limited to 500 profiles.")

    monkeypatch.setattr(SyntheticProfileRepository, "add", full)
    goto(at, "Fans")
    button(at, "Generate profile").click().run()
    button(at, "Add to demo dataset").click().run()
    assert not at.exception
    assert any("limited to 500" in w.value for w in at.warning)


# ------------------------------------------------------------------ OCR demo (M1 decisions)


def _name_input(at: AppTest) -> str:
    value = next(t for t in at.text_input if t.label == "Name to look for").value
    assert value
    return value


def run_ocr(at: AppTest) -> None:
    button(at, "Extract text and compare").click().run()
    assert not at.exception


def test_ocr_match_path(at: AppTest, monkeypatch: pytest.MonkeyPatch) -> None:
    goto(at, "OCR demo")
    name = _name_input(at)
    monkeypatch.setattr(ocr, "extract_text", lambda image, **_: f"Name: {name}")
    run_ocr(at)
    assert any("Match: the full name appears" in s.value for s in at.success)
    assert any(i.value == app_module.MATCHING_DISCLAIMER for i in at.info)


def test_ocr_rejects_words_that_are_present_but_not_in_sequence(
    at: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M0 accepted this (all words anywhere); the app's M1 rule does not."""
    goto(at, "OCR demo")
    words = _name_input(at).split()
    scrambled = "Name: " + " ".join(reversed(words)) + "\nCity: Vila Aurora"
    monkeypatch.setattr(ocr, "extract_text", lambda image, **_: scrambled)
    run_ocr(at)
    assert not at.success
    assert any("every word appears somewhere" in w.value for w in at.warning)


@pytest.mark.parametrize(
    ("ocr_text", "expected_message"),
    [
        ("first-word-only", "only some of the words"),
        ("Unrelated text", "none of the words"),
    ],
)
def test_ocr_partial_and_no_match_messages(
    at: AppTest, monkeypatch: pytest.MonkeyPatch, ocr_text: str, expected_message: str
) -> None:
    goto(at, "OCR demo")
    text = ocr_text.replace("first-word-only", _name_input(at).split()[0])
    monkeypatch.setattr(ocr, "extract_text", lambda image, **_: text)
    run_ocr(at)
    messages = [w.value for w in at.warning] + [e.value for e in at.error]
    assert any(expected_message in m for m in messages)


def test_ocr_blank_name_shows_friendly_error(at: AppTest, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "extract_text", lambda image, **_: "Name: someone")
    goto(at, "OCR demo")
    next(t for t in at.text_input if t.label == "Name to look for").set_value("   ").run()
    run_ocr(at)
    assert any("at least one letter" in e.value for e in at.error)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ocr.OCRUnavailableError("not installed"), "OCR is unavailable"),
        (ocr.OCRFailedError("engine crashed"), "OCR failed"),
        (ocr.OCRTimeoutError("OCR timed out."), "took too long"),
    ],
)
def test_ocr_errors_are_friendly(
    at: AppTest, monkeypatch: pytest.MonkeyPatch, error: Exception, message: str
) -> None:
    def failing(image: Image.Image, **_: object) -> str:
        raise error

    monkeypatch.setattr(ocr, "extract_text", failing)
    goto(at, "OCR demo")
    run_ocr(at)
    assert any(message in e.value for e in at.error)
    assert "traceback" not in all_text(at)


def test_ocr_result_persists_until_inputs_change(
    at: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    goto(at, "OCR demo")
    name = _name_input(at)
    monkeypatch.setattr(ocr, "extract_text", lambda image, **_: f"Name: {name}")
    run_ocr(at)
    at.run()  # an unrelated rerun keeps the result
    assert any("Match:" in s.value for s in at.success)
    at.slider[0].set_value(1.0).run()  # changing the capture clears it
    assert not at.success
    assert any("Run OCR to see" in c.value for c in at.caption)


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
    goto(at, "OCR demo")
    for _ in range(3):
        run_ocr(at)
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
        goto(at, "OCR demo")
        run_ocr(at)
    finally:
        guard.concurrency.release()
    assert any("busy" in w.value for w in at.warning)


def test_invalid_configuration_fails_closed_with_generic_message(
    make_app: Callable[[dict[str, str]], AppTest],
) -> None:
    at = make_app({"KYF_OCR_MAX_CONCURRENCY": "1000"})
    assert any("misconfigured" in e.value for e in at.error)
    assert not at.radio  # the app stopped before rendering navigation or any page
    assert "1000" not in all_text(at)


def test_storage_failure_while_rendering_a_page_is_handled(
    at: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_list(self: object) -> list[object]:
        raise StorageError("A demo database operation failed.")

    monkeypatch.setattr(SyntheticProfileRepository, "list_all", failing_list)
    goto(at, "Fans")
    assert not at.exception
    assert any("temporarily unavailable" in e.value for e in at.error)


@pytest.mark.parametrize("page", ["Fans", "OCR demo"])
def test_unexpected_errors_show_no_details_under_community_cloud_config(
    at: AppTest,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    page: str,
) -> None:
    # Community Cloud enforces client.showErrorDetails = false, which Streamlit renders
    # as "stacktrace". The app must not let any exception reach Streamlit's renderer.
    from streamlit import config as st_config

    marker = "/mount/src/secret-path/never-shown.py SECRET-MARKER"

    def broken(self: object) -> list[object]:
        raise RuntimeError(marker)

    original = st_config.get_option("client.showErrorDetails")
    st_config.set_option("client.showErrorDetails", False)
    try:
        monkeypatch.setattr(SyntheticProfileRepository, "list_all", broken)
        with caplog.at_level(logging.DEBUG):
            goto(at, page)
    finally:
        st_config.set_option("client.showErrorDetails", original)
    assert not at.exception
    assert [e.value for e in at.error] == [app_module.UNEXPECTED_ERROR_MESSAGE]
    assert "secret-marker" not in all_text(at)
    assert "SECRET-MARKER" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_ui_flows_do_not_log_names_or_ocr_text(
    at: AppTest, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ocr_output = "OCR-OUTPUT-SHOULD-NOT-BE-LOGGED"

    def timing_out(image: Image.Image, **_: object) -> str:
        raise ocr.OCRTimeoutError("OCR timed out.")

    with caplog.at_level(logging.DEBUG, logger="know_your_fan"):
        goto(at, "OCR demo")
        name = _name_input(at)
        monkeypatch.setattr(ocr, "extract_text", lambda image, **_: ocr_output)
        run_ocr(at)
        monkeypatch.setattr(ocr, "extract_text", timing_out)
        next(t for t in at.text_input if t.label == "Name to look for").set_value(
            "Zeferino Typed Name"
        ).run()
        run_ocr(at)
    for sensitive in (ocr_output, name, "Zeferino", "Typed Name"):
        assert sensitive not in caplog.text


# ------------------------------------------------------------------ research page


@pytest.fixture
def research_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "repo"
    monkeypatch.setattr(presentation, "REPO_ROOT", root)
    research_page.research_data.clear()
    yield root
    research_page.research_data.clear()


def _install_explorer(root: Path, **changes: object) -> None:
    data = json.loads((ROOT / presentation.EXPLORER_PATH).read_text(encoding="utf-8"))
    data.update(changes)
    target = root / presentation.EXPLORER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data), encoding="utf-8")


def test_research_page_without_results(at: AppTest, research_root: Path) -> None:
    goto(at, "Research")
    assert any("No research results" in w.value for w in at.warning)
    assert any("not identity-verification" in i.value for i in at.info)


def test_research_page_with_malformed_results(at: AppTest, research_root: Path) -> None:
    target = research_root / presentation.EXPLORER_PATH
    target.parent.mkdir(parents=True)
    target.write_text('{"status": "final"}', encoding="utf-8")  # missing required sections
    goto(at, "Research")
    assert any("No research results" in w.value for w in at.warning)


def test_research_page_shows_precomputed_results(at: AppTest, research_root: Path) -> None:
    _install_explorer(research_root)
    goto(at, "Research")
    assert any("Final results" in c.value for c in at.caption)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Real OCR runs"] == "19,200"
    assert metrics["Held-out test cards"] == "160"
    assert len(at.tabs) == 4
    assert len(at.get("vega_lite_chart")) >= 4  # degradation, preprocessing x2, sweep
    assert len(at.dataframe) >= 4  # every chart has a data table, plus the matching table


def test_research_page_controls_filter_the_data(at: AppTest, research_root: Path) -> None:
    _install_explorer(research_root)
    goto(at, "Research")
    family = next(s for s in at.selectbox if s.label == "Degradation family")
    family.set_value("rotation").run()
    assert not at.exception
    tables = [df.value for df in at.dataframe]
    rotation_table = next(t for t in tables if "Condition" in t.columns)
    assert set(rotation_table["Condition"]) == {"rot_-3", "rot_+3", "rot_-8", "rot_+8"}
    at.radio(key="deg_metric").set_value("WER").run()
    assert not at.exception


def test_research_page_marks_preliminary_results(at: AppTest, research_root: Path) -> None:
    _install_explorer(research_root, status="preliminary")
    goto(at, "Research")
    assert any("Preliminary results" in w.value for w in at.warning)


def test_research_page_never_runs_experiments(
    at: AppTest, research_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> str:
        raise AssertionError("the research page must not run OCR")

    monkeypatch.setattr(ocr, "recognize", forbidden)
    monkeypatch.setattr(ocr, "extract_text", forbidden)
    _install_explorer(research_root)
    goto(at, "Research")
    for tab_family in ("blur", "noise", "all"):
        next(s for s in at.selectbox if s.label == "Degradation family").set_value(tab_family).run()
    assert not at.exception


def test_home_falls_back_when_research_data_is_missing(at: AppTest, research_root: Path) -> None:
    at.run()
    assert not at.exception
    assert not at.metric  # no figures without the committed results
    assert "research results are not available" in all_text(at)


def test_committed_explorer_file_exists_and_is_loadable() -> None:
    assert (ROOT / presentation.EXPLORER_PATH).is_file()
    assert presentation.load_explorer(ROOT) is not None


def test_both_profile_cards_render_together(at: AppTest) -> None:
    """Regression: the Browse and Generate cards once shared a widget key and crashed."""
    goto(at, "Fans")
    button(at, "Generate profile").click().run()
    assert not at.exception
    assert len([c for c in at.caption if c.value == "Demo ID"]) == 2
