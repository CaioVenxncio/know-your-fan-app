"""Streamlit interface for the Know Your Fan synthetic-data demonstration.

This module contains presentation code only; workflows live in
:mod:`know_your_fan.services`. User-controlled or generated values are rendered
with ``st.text``, ``st.code``, ``st.metric`` or ``st.dataframe`` and never
interpolated into Markdown or HTML. The design system (tokens, styles, helpers)
lives in :mod:`know_your_fan.ui` and ``.streamlit/config.toml``.
"""

from __future__ import annotations

import logging
import random
import uuid
from pathlib import Path
from typing import Any

import streamlit as st

from know_your_fan import services, ui
from know_your_fan.config import ConfigurationError, load_settings
from know_your_fan.limits import ResourceLimitError
from know_your_fan.models import FanProfile
from know_your_fan.observability import LOGGER_NAME, configure_logging
from know_your_fan.ocr import (
    MAX_BLUR_RADIUS,
    MAX_ROTATION_DEGREES,
    InvalidImageError,
    OCRFailedError,
    OCRTimeoutError,
    OCRUnavailableError,
)
from know_your_fan.research import presentation
from know_your_fan.research_page import research_data
from know_your_fan.storage import StorageBusyError, StorageError, StorageLimitError
from know_your_fan.synthetic import GAMES, generate_profile
from know_your_fan.text_matching import MAX_EXPECTED_NAME_LENGTH

MAX_SEED = 1_000_000_000

SYNTHETIC_NOTICE = ui.SYNTHETIC_NOTICE  # shown by ui.page_header on every page
MATCHING_DISCLAIMER = "Text matching demonstration — not identity verification."
UNEXPECTED_ERROR_MESSAGE = "Something went wrong on this page. Please reload or try another page."

PAGES = ("Home", "Fans", "OCR demo", "Research")
# Home's primary actions double as the way into each section (button label -> page).
HOME_ACTIONS = {
    "Fans": "Explore fans",
    "OCR demo": "Run the OCR demo",
    "Research": "Read the study",
}

_logger = logging.getLogger(f"{LOGGER_NAME}.app")
_SESSION_KEY = "kyf_session_key"
_RESULT_KEY = "ocr_result"
_FAN_SELECT_KEY = "fan_profile"
_FAN_TABLE_KEY = "fans_table"
_FAN_TABLE_APPLIED = "fans_table_applied"


@st.cache_resource
def get_runtime() -> services.Runtime:
    """Load settings and build process-wide limits and storage once per process."""
    configure_logging()
    return services.build_runtime(load_settings())


def session_key() -> str:
    """Random per-session identifier for per-session limits (not a security boundary)."""
    key = st.session_state.get(_SESSION_KEY)
    if not isinstance(key, str):
        key = uuid.uuid4().hex
        st.session_state[_SESSION_KEY] = key
    return key


def _profile_label(profile: FanProfile) -> str:
    return f"{profile.name} · {profile.demo_id}"


def _field(column: Any, label: str, value: str) -> None:
    column.caption(label)
    column.text(value)


def show_profile_card(profile: FanProfile, context: str) -> None:
    """Profile panel. All values are generated data rendered as plain text."""
    with st.container(border=True, key=f"{ui.PANEL_KEY}_profile_{context}"):
        mark, title = st.columns([1, 7], vertical_alignment="center")
        with mark:
            ui.monogram(profile.name)
        with title, st.container(key=f"{ui.PROFILE_NAME_KEY}_{context}"):  # unique per card
            st.text(profile.name)
        _field(st, "Demo ID", profile.demo_id)
        first = st.columns(2)
        _field(first[0], "City (fictional)", profile.city)
        _field(first[1], "Favourite game", profile.interests[0])
        second = st.columns(2)
        _field(second[0], "Games", "\n".join(profile.interests))
        _field(second[1], "Purchases (demo items)", "\n".join(profile.purchases) or "none")
        _field(st, "In the last year", "\n".join(profile.activities))
        st.caption("Links (reserved .example domain, not real accounts)")
        st.code(
            "\n".join(profile.social_links + profile.esports_profiles),
            language=None,
            wrap_lines=True,  # no horizontal scroll region on phones
        )


# ---------------------------------------------------------------- Home


def page_home() -> None:
    explorer = research_data()
    scope = presentation.study_scope(explorer) if explorer else None
    ui.page_header(
        "Know Your Fan",
        "An independent software engineering and research project: generated esports fan "
        "profiles, Tesseract OCR on a fictional fan card, and a pre-registered study of how "
        "reliably a name can be found in OCR output.",
    )

    actions, study = st.columns([7, 5], gap="large")
    with actions:
        st.header("Explore", anchor=False)
        details = {
            "Fans": "Browse the seeded fictional profiles, or generate one from a numeric seed.",
            "OCR demo": "Blur or rotate a fictional fan card and check whether OCR still reads "
            "the name.",
            "Research": "Measured error rates, with confidence intervals, from the "
            "pre-registered study.",
        }
        for target, label in HOME_ACTIONS.items():
            with st.container(key=f"home_action_{target.split()[0].lower()}"):
                text, button = st.columns([5, 2], vertical_alignment="center")
                text.markdown(f"**{target}**  \n:gray[{details[target]}]")
                if button.button(label, key=f"home_{target}", width="stretch"):
                    st.switch_page(page_script(target))
    with study, st.container(border=True, key=f"{ui.PANEL_KEY}_study"):
        st.subheader("The study in brief", anchor=False)
        if scope is None:
            st.caption("Research results are not available in this deployment.")
        else:
            figures = st.columns(3)
            figures[0].metric("Synthetic cards", f"{scope['cards']:,}")
            figures[1].metric("OCR runs", f"{scope['ocr_runs']:,}")
            figures[2].metric("Matching rules", f"{scope['matching_rules']}")
            matching = explorer["test_matching"]["P0_baseline"] if explorer else {}
            m0, m1 = matching["M0_baseline"], matching["M1_token_sequence"]
            decoys = m0["fp"] + m0["tn"]
            st.markdown(
                f"On held-out cards, the original rule accepted **{m0['fp']} of {decoys:,}** "
                f"decoy names; the sequence rule the app now uses accepted **{m1['fp']}**. "
                ":gray[Synthetic cards only.]"
            )

    st.header("How the OCR demo works", anchor=False)
    steps = (
        ("Draw", "The app renders a fictional fan card, watermarked as a specimen."),
        ("Degrade", "Blur and rotation simulate a poor capture."),
        ("Read", "Tesseract OCR extracts the text on the server."),
        ("Match", "The name must appear as a whole word sequence on one line. Accents and "
         "capitals are ignored; partial words never count."),
    )  # fmt: skip
    for number, (column, (step_title, step_text)) in enumerate(
        zip(st.columns(4, gap="medium"), steps, strict=True), start=1
    ):
        with column:
            ui.step_number(number)
            st.markdown(f"**{step_title}**  \n:gray[{step_text}]")

    st.header("Boundaries", anchor=False)
    synthetic, verification = st.columns(2, gap="large")
    synthetic.markdown(
        "**Everything is synthetic.** Real names, CPF numbers, addresses and ID documents are "
        "personal data, and a public demo has no reason to collect them. Every profile and "
        "card is generated, and there are no uploads."
    )
    verification.markdown(
        "**A match is not identity verification.** It only shows that OCR recognised the "
        "words in an image this app drew. It is not document authentication or fraud "
        "detection, and the study's results do not transfer to real documents."
    )


# ---------------------------------------------------------------- Fans


def page_fans() -> None:
    ui.page_header(
        "Fans",
        "Fictional esports fans, each generated from a seed. Open a profile from the table, "
        "or generate a new one.",
    )
    runtime = get_runtime()
    profiles = runtime.repository.list_all()
    browse, generate = st.tabs(["Browse", "Generate"])
    with browse:
        _browse(profiles)
    with generate:
        _generate(runtime)


def _browse(profiles: list[FanProfile]) -> None:
    search, games_filter = st.columns([3, 2])
    query = search.text_input(
        "Search name or city",
        max_chars=services.MAX_SEARCH_LENGTH,
        placeholder="e.g. Lima or Vila Aurora",
    )
    games = games_filter.multiselect("Favourite games", GAMES, placeholder="Any game")
    filtered = services.filter_profiles(profiles, query, games)
    if not filtered:
        st.info("No fictional fans match these filters. Try a shorter search or clear the games.")
        return
    table, detail = st.columns([7, 5], gap="large")
    with table:
        st.caption(f"{len(filtered)} of {len(profiles)} profiles · select a row to open it")
        event = st.dataframe(
            [{"Name": p.name, "City": p.city, "Favourite game": p.interests[0]} for p in filtered],
            hide_index=True,
            width="stretch",
            height=min(38 + 35 * len(filtered), 460),
            on_select="rerun",
            selection_mode="single-row",
            key=_FAN_TABLE_KEY,
        )
    _apply_table_selection(event, filtered, (query, tuple(games)))
    with detail:
        selected = st.selectbox(
            "Open profile", filtered, format_func=_profile_label, key=_FAN_SELECT_KEY
        )
        if selected is not None:
            show_profile_card(selected, "browse")


def _apply_table_selection(
    event: Any, filtered: list[FanProfile], filters: tuple[str, tuple[str, ...]]
) -> None:
    """Let a newly selected table row drive the profile select box (and nothing else)."""
    if st.session_state.get(_FAN_SELECT_KEY) not in filtered:
        st.session_state.pop(_FAN_SELECT_KEY, None)
    rows = getattr(getattr(event, "selection", None), "rows", None) or []
    if not rows or rows[0] >= len(filtered):
        return
    marker = (rows[0], filters)
    if st.session_state.get(_FAN_TABLE_APPLIED) != marker:
        st.session_state[_FAN_TABLE_APPLIED] = marker
        st.session_state[_FAN_SELECT_KEY] = filtered[rows[0]]


def _generate(runtime: services.Runtime) -> None:
    controls, preview = st.columns([2, 3], gap="large")
    with controls:
        st.markdown(
            ":gray[The same seed always gives the same fictional fan. There are no free-text "
            "fields, so nothing typed by a visitor is stored.]"
        )
        seed = st.number_input("Seed", min_value=0, max_value=MAX_SEED, value=0, step=1)
        if st.button("Generate profile", type="primary", width="stretch"):
            st.session_state["generated_profile"] = generate_profile(random.Random(int(seed)))
    with preview:
        profile = st.session_state.get("generated_profile")
        if not isinstance(profile, FanProfile):
            st.caption("Pick a seed and generate a profile to preview it here.")
            return
        show_profile_card(profile, "generate")
        if st.button("Add to demo dataset"):
            try:
                added = services.add_generated_profile(runtime, profile, session_key())
            except (StorageLimitError, StorageBusyError, ResourceLimitError) as exc:
                st.warning(str(exc))
            else:
                if added:
                    st.success("Fictional profile added to the demo dataset.")
                else:
                    st.info("This profile is already in the demo dataset.")


# ---------------------------------------------------------------- OCR demo


def page_ocr_demo() -> None:
    runtime = get_runtime()
    ui.page_header(
        "OCR demo",
        "Pick a fictional card, simulate a poor capture, and see whether Tesseract's output "
        "contains the name as a whole sequence of words on one line.",
    )
    st.info(MATCHING_DISCLAIMER, icon=":material/info:")
    profiles = runtime.repository.list_all()
    if not profiles:
        st.warning("The demo dataset is empty.")
        return

    specimen, outcome = st.columns([5, 6], gap="large")
    with specimen:
        st.header("Specimen", anchor=False)
        profile = st.selectbox("Fictional card", profiles, format_func=_profile_label)
        image_slot = st.container()
        blur_col, rotation_col = st.columns(2)
        blur = blur_col.slider(
            "Blur (Gaussian radius)", 0.0, MAX_BLUR_RADIUS, 0.0, 0.5,
            help="Simulates an out-of-focus capture.",
        )  # fmt: skip
        max_rotation = int(MAX_ROTATION_DEGREES)
        rotation = rotation_col.slider(
            "Rotation (degrees)", -max_rotation, max_rotation, 0,
            help="Simulates a tilted camera.",
        )  # fmt: skip
        expected = st.text_input(
            "Name to look for",
            value=profile.name,
            max_chars=MAX_EXPECTED_NAME_LENGTH,
            key=f"expected_name_{profile.demo_id}",
            help="Edit it to see how near-miss names are handled. Nothing typed is stored.",
        )
        image = services.render_card(profile, blur_radius=blur, rotation_degrees=rotation)
        image_slot.image(
            image,
            caption="Fictional specimen card generated by the app (synthetic data).",
            alt=(
                "Fictional specimen fan card, as sent to OCR, with lines for name, demo ID, "
                "city and favourite game"
            ),
            width="stretch",
        )
        inputs = (profile.demo_id, blur, rotation, expected)
        if st.button("Extract text and compare", type="primary", width="stretch"):
            st.session_state[_RESULT_KEY] = {"inputs": inputs, **_run_ocr(runtime, image, expected)}
    with outcome:
        st.header("Result", anchor=False)
        result = st.session_state.get(_RESULT_KEY)
        if isinstance(result, dict) and result.get("inputs") == inputs:
            _show_result(result)
        else:
            st.caption(
                "Run OCR to see the recognised text and the matching result. A result stays "
                "here until you change the card, the capture, or the name."
            )
        with st.expander("Why does OCR sometimes miss the name?"):
            st.write(
                "In the project's synthetic study, clean cards were read almost perfectly. Most "
                "failures came from **rotation of about 8°**, **strong blur**, and **very low "
                "resolution**: the engine then misreads or drops whole lines, and no matching "
                "rule can recover words it never produced. Small rotations of the same size can "
                "behave differently depending on direction. The Research page has the measured "
                "numbers."
            )


def _run_ocr(runtime: services.Runtime, image: Any, expected: str) -> dict[str, Any]:
    """Run the OCR workflow and return a display-ready result (never raises)."""
    try:
        with st.spinner("Running OCR on the fictional card..."):
            outcome = services.run_text_matching(
                image,
                expected,
                guard=runtime.ocr_guard,
                session_key=session_key(),
                settings=runtime.settings,
            )
    except ResourceLimitError as exc:
        return {"kind": "limited", "message": str(exc)}
    except OCRUnavailableError:
        return {"kind": "error", "message": "OCR is unavailable in this environment."}
    except OCRTimeoutError:
        return {
            "kind": "error",
            "message": "OCR took too long and was stopped. Try less blur or rotation.",
        }
    except (OCRFailedError, InvalidImageError) as exc:
        return {"kind": "error", "message": f"OCR failed: {exc}"}
    except ValueError as exc:
        return {"kind": "error", "message": str(exc)}
    words = outcome.match.words
    return {
        "kind": "ok",
        "verdict": outcome.match.verdict,
        "found": list(words.found_tokens),
        "missing": list(words.missing_tokens),
        "text": outcome.extracted_text,
    }


_VERDICTS = {
    "match": (
        "success",
        ":material/check_circle:",
        "Match: the full name appears, in order, on one line of the text.",
    ),
    "words_not_in_sequence": (
        "warning",
        ":material/swap_horiz:",
        "No match: every word appears somewhere, but not as this name on one line. "
        "The original rule would have accepted this; the app now requires the full sequence.",
    ),
    "partial": ("warning", ":material/rule:", "No match: only some of the words were found."),
    "none": (
        "error",
        ":material/cancel:",
        "No match: none of the words were found in the extracted text.",
    ),
}


def _display_text(text: str) -> str:
    """OCR output without the blank lines Tesseract puts between lines (display only)."""
    return "\n".join(line for line in text.splitlines() if line.strip())


def _show_result(result: dict[str, Any]) -> None:
    if result["kind"] == "limited":
        st.warning(result["message"], icon=":material/hourglass_top:")
        return
    if result["kind"] == "error":
        st.error(result["message"], icon=":material/error:")
        return
    level, icon, message = _VERDICTS[result["verdict"]]
    getattr(st, level)(message, icon=icon)
    found, missing = st.columns(2)
    _field(found, "Words found", ", ".join(result["found"]) or "—")
    _field(missing, "Words missing", ", ".join(result["missing"]) or "—")
    st.caption("Recognised text (Tesseract output)")
    st.code(_display_text(result["text"]) or "(no text recognised)", language=None, wrap_lines=True)
    st.caption(MATCHING_DISCLAIMER)


# ---------------------------------------------------------------- shell


# Each section is a tiny script in page_scripts/ that calls its render function. File
# pages (rather than callables) keep the selected page across reruns in AppTest as well
# as in the browser, through Streamlit's public API.
PAGE_SCRIPTS_DIR = Path(__file__).resolve().parent / "page_scripts"
_PAGE_SPECS = {
    "Home": ("home.py", ":material/home:", "home"),
    "Fans": ("fans.py", ":material/groups:", "fans"),
    "OCR demo": ("ocr_demo.py", ":material/document_scanner:", "ocr-demo"),
    "Research": ("research.py", ":material/monitoring:", "research"),
}


def page_script(title: str) -> Path:
    return PAGE_SCRIPTS_DIR / _PAGE_SPECS[title][0]


def _navigation() -> Any:
    pages = [
        st.Page(page_script(title), title=title, icon=icon, url_path=path, default=title == "Home")
        for title, (_, icon, path) in _PAGE_SPECS.items()
    ]
    # Top navigation: one compact row in the app header, full content width, and no sidebar
    # on desktop. On narrow screens Streamlit moves it into its standard navigation drawer.
    return st.navigation(pages, position="top")


def main() -> None:
    wordmark, mark = ui.brand_assets()
    st.set_page_config(
        page_title="Know Your Fan",
        page_icon=str(mark),
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    ui.apply_theme()
    st.logo(str(wordmark), icon_image=str(wordmark), size="large")  # name visible on every page
    try:
        get_runtime()
    except ConfigurationError:
        _logger.error("Invalid configuration; the app will not start")
        st.error("The demo is misconfigured and cannot start. Please contact the operator.")
        st.stop()
    except StorageError as exc:
        st.error(f"The demo dataset is unavailable: {exc}")
        st.stop()
    except Exception as exc:
        _logger.error("Unexpected error during start-up (%s)", type(exc).__name__)
        st.error(UNEXPECTED_ERROR_MESSAGE)
        st.stop()
    navigation = _navigation()
    try:
        navigation.run()
    except StorageError as exc:
        st.error(f"The demo dataset is temporarily unavailable: {exc}")
    except Exception as exc:
        # Last line of defence: never let Streamlit render an uncaught exception.
        # Streamlit Community Cloud enforces client.showErrorDetails = false, which
        # Streamlit treats as "stacktrace", overriding .streamlit/config.toml.
        # Streamlit's stop/rerun/switch-page signals derive from BaseException and pass through.
        _logger.error("Unexpected error while rendering a page (%s)", type(exc).__name__)
        st.error(UNEXPECTED_ERROR_MESSAGE)
    st.divider()
    st.caption(
        "Independent portfolio project. Not affiliated with any esports organization. "
        "MIT licensed. Synthetic data only."
    )
