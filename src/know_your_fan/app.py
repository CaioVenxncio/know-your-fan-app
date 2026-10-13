"""Streamlit interface for the Know Your Fan synthetic-data demonstration.

This module contains presentation code only; workflows live in
:mod:`know_your_fan.services`. User-controlled or generated values are rendered
with ``st.text``, ``st.code``, ``st.metric`` or ``st.dataframe`` and never
interpolated into Markdown or HTML. Static styling lives in :mod:`know_your_fan.ui`.
"""

from __future__ import annotations

import logging
import random
import uuid
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
from know_your_fan.research_page import page_research, research_data
from know_your_fan.storage import StorageBusyError, StorageError, StorageLimitError
from know_your_fan.synthetic import GAMES, generate_profile
from know_your_fan.text_matching import MAX_EXPECTED_NAME_LENGTH

MAX_SEED = 1_000_000_000

SYNTHETIC_NOTICE = (
    "Synthetic-data demonstration. All profiles and documents are fictional. "
    "Do not enter real names, CPF numbers, addresses, or identity documents."
)
MATCHING_DISCLAIMER = "Text matching demonstration — not identity verification."

PAGES = ("Home", "Fans", "OCR demo", "Research")
NAV_KEY = "nav"

_logger = logging.getLogger(f"{LOGGER_NAME}.app")
_SESSION_KEY = "kyf_session_key"
_RESULT_KEY = "ocr_result"


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


def _go_to(page: str) -> None:
    st.session_state[NAV_KEY] = page


def _profile_label(profile: FanProfile) -> str:
    return f"{profile.name} · {profile.demo_id}"


def show_profile_card(profile: FanProfile, context: str) -> None:
    """Profile card. All values are generated data rendered as plain text."""
    with st.container(border=True):
        ui.eyebrow("Fictional fan profile")
        with st.container(key=f"{ui.PROFILE_NAME_KEY}_{context}"):  # unique per card
            st.text(profile.name)  # shown as a title by the static profile_name style
        top = st.columns(3)
        for column, label, value in zip(
            top,
            ("Demo ID", "City (fictional)", "Favourite game"),
            (profile.demo_id, profile.city, profile.interests[0]),
            strict=True,
        ):
            column.caption(label)
            column.text(value)
        left, right = st.columns(2)
        with left:
            st.caption("Interests")
            st.text("\n".join(f"• {i}" for i in profile.interests))
            st.caption("Activities in the last year")
            st.text("\n".join(f"• {a}" for a in profile.activities))
        with right:
            st.caption("Purchases (demo items)")
            st.text("\n".join(f"• {p}" for p in profile.purchases) or "• none")
            st.caption("Links (reserved .example domain, not real accounts)")
            st.code("\n".join(profile.social_links + profile.esports_profiles), language=None)


# ---------------------------------------------------------------- Home


def page_home() -> None:
    ui.hero(
        "Fictional esports fans, real OCR, honest numbers.",
        "Know Your Fan is an independent software engineering and research project. Explore "
        "generated fan profiles, watch OCR read a fictional fan card, and see what a "
        "pre-registered experiment measured about matching names in OCR output.",
    )
    explorer = research_data()
    research_text = (
        f"{presentation.total_ocr_runs(explorer):,} real OCR runs on synthetic cards."
        if explorer
        else "A pre-registered OCR study on synthetic cards."
    )
    cards = st.columns(3)
    entries = (
        ("Explore fans", "Browse and generate fictional fan profiles.", "Fans"),
        ("Try the OCR demo", "Degrade a fictional card and match a name.", "OCR demo"),
        ("Read the research", research_text, "Research"),
    )
    for column, (title, text, target) in zip(cards, entries, strict=True):
        with column.container(border=True):
            st.subheader(title)
            st.write(text)
            st.button(
                f"Open {target}", key=f"home_{target}", on_click=_go_to, args=(target,),
                width="stretch",
            )  # fmt: skip

    st.divider()
    how, why = st.columns([3, 2])
    with how:
        ui.eyebrow("How the text matching works")
        st.write(
            "1. The app **draws a fictional fan card** (watermarked as a specimen).\n"
            "2. You can **blur or rotate** it to simulate a poor capture.\n"
            "3. **Tesseract OCR** extracts the text from the image.\n"
            "4. The app checks whether the **name appears, as a whole sequence of words, on one "
            "line** of that text. Accents and capitals are ignored; partial words never count."
        )
    with why:
        ui.eyebrow("Why everything is synthetic")
        st.write(
            "Real names, CPF numbers, addresses, and ID documents are personal data. A public "
            "demo has no reason to collect them, so it never does: every profile and card is "
            "generated, and there are no uploads."
        )
    with st.container(border=True):
        ui.eyebrow("What this is not")
        st.write(
            "Finding a name in OCR text only shows that the words were recognised in an image "
            "this app drew. It is **not identity verification**, document authentication, or "
            "fraud detection, and the research results do not transfer to real documents."
        )


# ---------------------------------------------------------------- Fans


def page_fans(runtime: services.Runtime) -> None:
    ui.eyebrow("Synthetic fan profiles")
    st.header("Fans")
    browse, generate = st.tabs(["Browse", "Generate"])
    with browse:
        _browse(runtime)
    with generate:
        _generate(runtime)


def _browse(runtime: services.Runtime) -> None:
    profiles = runtime.repository.list_all()
    left, right = st.columns([3, 2])
    query = left.text_input(
        "Search name or city",
        max_chars=services.MAX_SEARCH_LENGTH,
        placeholder="e.g. Lima or Vila Aurora",
    )
    games = right.multiselect("Favourite games", GAMES, placeholder="Any game")
    filtered = services.filter_profiles(profiles, query, games)
    st.caption(f"{len(filtered)} of {len(profiles)} fictional profiles")
    if not filtered:
        st.info("No fictional fans match these filters. Try a shorter search or clear the games.")
        return
    st.dataframe(
        [
            {
                "Name": p.name,
                "City": p.city,
                "Games": ", ".join(p.interests),
                "Demo ID": p.demo_id,
            }
            for p in filtered
        ],
        hide_index=True,
        width="stretch",
        height=min(38 + 35 * len(filtered), 320),
    )
    selected = st.selectbox("Show profile", filtered, format_func=_profile_label)
    if selected is not None:
        show_profile_card(selected, "browse")


def _generate(runtime: services.Runtime) -> None:
    st.write(
        "Profiles are generated from a seed, so the same seed always gives the same fictional "
        "fan. There are no free-text fields, so nothing typed by a visitor is stored."
    )
    seed_col, button_col = st.columns([2, 1], vertical_alignment="bottom")
    seed = seed_col.number_input("Seed", min_value=0, max_value=MAX_SEED, value=0, step=1)
    if button_col.button("Generate profile", type="primary", width="stretch"):
        st.session_state["generated_profile"] = generate_profile(random.Random(int(seed)))
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


def page_ocr_demo(runtime: services.Runtime) -> None:
    ui.eyebrow("Text matching on a fictional card")
    st.header("OCR demo")
    st.info(MATCHING_DISCLAIMER)
    profiles = runtime.repository.list_all()
    if not profiles:
        st.warning("The demo dataset is empty.")
        return

    controls, preview = st.columns([2, 3], gap="large")
    with controls:
        ui.step(1, "Pick a card and a capture")
        profile = st.selectbox("Fictional profile", profiles, format_func=_profile_label)
        blur = st.slider(
            "Blur (Gaussian radius)", 0.0, MAX_BLUR_RADIUS, 0.0, 0.5,
            help="Simulates an out-of-focus capture.",
        )  # fmt: skip
        max_rotation = int(MAX_ROTATION_DEGREES)
        rotation = st.slider(
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
    with preview:
        st.image(
            image,
            caption="Fictional specimen card generated by the app (synthetic data).",
            width="stretch",
        )

    ui.step(2, "Run OCR and compare")
    inputs = (profile.demo_id, blur, rotation, expected)
    if st.button("Extract text and compare", type="primary"):
        st.session_state[_RESULT_KEY] = {"inputs": inputs, **_run_ocr(runtime, image, expected)}
    result = st.session_state.get(_RESULT_KEY)
    if isinstance(result, dict) and result.get("inputs") == inputs:
        ui.step(3, "Result")
        _show_result(result)
    else:
        st.caption("Run OCR to see the extracted text and the matching result.")
    with st.expander("Why does OCR sometimes miss the name?"):
        st.write(
            "In the project's synthetic study, clean cards were read almost perfectly. Most "
            "failures came from **rotation of about 8°**, **strong blur**, and **very low "
            "resolution**: the engine then misreads or drops whole lines, and no matching rule "
            "can recover words it never produced. Small rotations of the same size can behave "
            "differently depending on direction. See the Research section for measured numbers."
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


def _show_result(result: dict[str, Any]) -> None:
    if result["kind"] == "limited":
        st.warning(result["message"], icon=":material/hourglass_top:")
        return
    if result["kind"] == "error":
        st.error(result["message"], icon=":material/error:")
        return
    level, icon, message = _VERDICTS[result["verdict"]]
    getattr(st, level)(message, icon=icon)
    st.caption(MATCHING_DISCLAIMER)
    found, missing = st.columns(2)
    found.caption("Words found")
    found.text(", ".join(result["found"]) or "—")
    missing.caption("Words missing")
    missing.text(", ".join(result["missing"]) or "—")
    st.caption("Extracted text (OCR output)")
    st.code(result["text"] or "(no text recognized)", language=None, wrap_lines=True)


# ---------------------------------------------------------------- shell


def main() -> None:
    st.set_page_config(
        page_title="Know Your Fan · synthetic OCR demo",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    ui.apply_theme()
    ui.brand_bar()
    st.caption(SYNTHETIC_NOTICE)
    try:
        runtime = get_runtime()
    except ConfigurationError:
        _logger.error("Invalid configuration; the app will not start")
        st.error("The demo is misconfigured and cannot start. Please contact the operator.")
        st.stop()
    except StorageError as exc:
        st.error(f"The demo dataset is unavailable: {exc}")
        st.stop()
    if st.session_state.get(NAV_KEY) not in PAGES:
        st.session_state[NAV_KEY] = PAGES[0]
    page = st.radio("Section", PAGES, horizontal=True, key=NAV_KEY, label_visibility="collapsed")
    try:
        if page == "Home":
            page_home()
        elif page == "Fans":
            page_fans(runtime)
        elif page == "OCR demo":
            page_ocr_demo(runtime)
        else:
            page_research()
    except StorageError as exc:
        st.error(f"The demo dataset is temporarily unavailable: {exc}")
    st.divider()
    st.caption(
        "Independent portfolio project. Not affiliated with any esports organization. "
        "MIT licensed. Synthetic data only."
    )
