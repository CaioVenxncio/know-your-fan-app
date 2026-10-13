"""Streamlit interface for the Know Your Fan synthetic-data demonstration.

This module contains presentation code only; workflows live in
:mod:`know_your_fan.services`. User-controlled or generated values are rendered
with ``st.text``, ``st.code`` or ``st.dataframe`` and never interpolated into
Markdown.
"""

from __future__ import annotations

import logging
import random
import uuid

import streamlit as st

from know_your_fan import services
from know_your_fan.config import ConfigurationError, load_settings
from know_your_fan.limits import ResourceLimitError
from know_your_fan.models import FanProfile
from know_your_fan.observability import LOGGER_NAME, configure_logging
from know_your_fan.ocr import (
    MAX_BLUR_RADIUS,
    MAX_ROTATION_DEGREES,
    InvalidImageError,
    OCRFailedError,
    OCRUnavailableError,
)
from know_your_fan.research import presentation
from know_your_fan.storage import StorageBusyError, StorageError, StorageLimitError
from know_your_fan.synthetic import GAMES, generate_profile
from know_your_fan.text_matching import MAX_EXPECTED_NAME_LENGTH

MAX_SEED = 1_000_000_000

SYNTHETIC_NOTICE = (
    "Synthetic-data demonstration. All profiles and documents are fictional. "
    "Do not enter real names, CPF numbers, addresses, or identity documents."
)
MATCHING_DISCLAIMER = "Text matching demonstration — not identity verification."

PAGES = ("About", "Fan explorer", "Profile generator", "Text-matching demo", "Research")


_logger = logging.getLogger(f"{LOGGER_NAME}.app")
_SESSION_KEY = "kyf_session_key"


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
    return f"{profile.demo_id} — {profile.name}"


def show_profile_details(profile: FanProfile) -> None:
    st.text(f"Demo ID: {profile.demo_id}")
    st.text(f"Name: {profile.name}")
    st.text(f"City (fictional): {profile.city}")
    st.text("Interests: " + ", ".join(profile.interests))
    st.text("Activities:\n" + "\n".join(f"- {a}" for a in profile.activities))
    st.text("Purchases:\n" + ("\n".join(f"- {p}" for p in profile.purchases) or "- none"))
    st.caption("Social links (reserved .example domain, not real accounts)")
    st.code("\n".join(profile.social_links), language=None)
    st.caption("Esports profiles (reserved .example domain, not real accounts)")
    st.code("\n".join(profile.esports_profiles), language=None)


def page_about() -> None:
    st.header("About this demo")
    st.write(
        "Know Your Fan explores two ideas: building esports fan profiles and extracting text "
        "from document images. This public version works only with synthetic data."
    )
    st.subheader("What it does")
    st.write(
        "- Browse a dataset of generated, fictional fan profiles.\n"
        "- Generate new fictional profiles from a seed.\n"
        "- Render a fictional fan card, run OCR on it, and check which words of a name appear "
        "in the extracted text."
    )
    st.subheader("What it does not do")
    st.write(
        "- It does not collect real personal data or accept document uploads.\n"
        "- It does not verify identity, detect forgeries, or authenticate documents. "
        "Finding a name in OCR text only shows that the text was recognized."
    )


def page_explorer(runtime: services.Runtime) -> None:
    st.header("Synthetic fan explorer")
    profiles = runtime.repository.list_all()
    query = st.text_input("Search name or city", max_chars=services.MAX_SEARCH_LENGTH)
    games = st.multiselect("Filter by game", GAMES)
    filtered = services.filter_profiles(profiles, query, games)
    st.caption(f"{len(filtered)} of {len(profiles)} fictional profiles")
    st.dataframe(
        [
            {
                "Demo ID": p.demo_id,
                "Name": p.name,
                "City": p.city,
                "Interests": ", ".join(p.interests),
            }
            for p in filtered
        ],
        hide_index=True,
        width="stretch",
    )
    if filtered:
        selected = st.selectbox("Profile details", filtered, format_func=_profile_label)
        if selected is not None:
            show_profile_details(selected)


def page_generator(runtime: services.Runtime) -> None:
    st.header("Fictional profile generator")
    st.write(
        "Profiles are generated from a seed. There are no free-text fields, "
        "so nothing typed by a visitor is stored."
    )
    seed = st.number_input("Seed", min_value=0, max_value=MAX_SEED, value=0, step=1)
    if st.button("Generate profile"):
        st.session_state["generated_profile"] = generate_profile(random.Random(int(seed)))
    profile = st.session_state.get("generated_profile")
    if not isinstance(profile, FanProfile):
        return
    show_profile_details(profile)
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


def page_text_matching(runtime: services.Runtime) -> None:
    st.header("Text-matching demo")
    st.info(MATCHING_DISCLAIMER)
    profiles = runtime.repository.list_all()
    if not profiles:
        st.warning("The demo dataset is empty.")
        return
    profile = st.selectbox("Fictional profile", profiles, format_func=_profile_label)
    col1, col2 = st.columns(2)
    blur = col1.slider("Blur radius", 0.0, MAX_BLUR_RADIUS, 0.0, 0.5)
    max_rotation = int(MAX_ROTATION_DEGREES)
    rotation = col2.slider("Rotation (degrees)", -max_rotation, max_rotation, 0)
    image = services.render_card(profile, blur_radius=blur, rotation_degrees=rotation)
    st.image(image, caption="Fictional specimen card (synthetic data)")

    expected = st.text_input(
        "Name to look for in the extracted text",
        value=profile.name,
        max_chars=MAX_EXPECTED_NAME_LENGTH,
        key=f"expected_name_{profile.demo_id}",
    )
    if not st.button("Extract text and compare"):
        return
    try:
        with st.spinner("Running OCR..."):
            outcome = services.run_text_matching(
                image,
                expected,
                guard=runtime.ocr_guard,
                session_key=session_key(),
                settings=runtime.settings,
            )
    except ResourceLimitError as exc:
        st.warning(str(exc))
        return
    except OCRUnavailableError as exc:
        st.error(f"OCR is unavailable in this environment: {exc}")
        return
    except (OCRFailedError, InvalidImageError) as exc:
        st.error(f"OCR failed: {exc}")
        return
    except ValueError as exc:
        st.error(str(exc))
        return

    result = outcome.match
    if result.all_found:
        st.success("All words of the name were found in the extracted text.")
    elif result.found_tokens:
        st.warning(f"Some words were found ({result.coverage:.0%} of the name).")
    else:
        st.warning("None of the words of the name were found in the extracted text.")
    st.caption(MATCHING_DISCLAIMER)
    st.text("Found: " + (", ".join(result.found_tokens) or "—"))
    st.text("Missing: " + (", ".join(result.missing_tokens) or "—"))
    st.caption("Extracted text (OCR)")
    st.code(outcome.extracted_text or "(no text recognized)", language=None)


@st.cache_data(show_spinner=False)
def _research_results() -> presentation.ResearchResults:
    return presentation.load_results()


def page_research() -> None:
    st.header("Research: OCR text matching on synthetic cards")
    st.info(
        "Synthetic-data study. These results describe OCR transcription and name matching on "
        "fictional cards rendered by this app. They are not identity-verification, "
        "document-authentication, or fraud-detection performance."
    )
    results = _research_results()
    if not results.available or results.summary is None:
        st.warning("No research results are available in this deployment.")
        return
    if results.is_final:
        st.success("Final results: held-out test split, choices frozen on dev/val beforehand.")
    else:
        st.warning("Preliminary results: the held-out test evaluation is not complete.")
    st.subheader("Question")
    st.write(
        "How do controlled image degradations and text-matching strategies affect the "
        "reliability, error rates, and computational cost of OCR-based name matching on "
        "synthetic specimen cards?"
    )
    st.subheader("Method in brief")
    st.write(
        "- Fictional names in disjoint dev / val / test splits (80 / 80 / 160 cards), "
        "1 true name and 3 decoy names per card.\n"
        "- 16 controlled degradations (blur, rotation, noise, resolution, combinations), "
        "8 preprocessing strategies, 4 matching strategies, real Tesseract OCR.\n"
        "- Choices (preprocessing, matching threshold) were frozen on dev/val before the test "
        "run; 95% intervals use a card-level bootstrap.\n"
        "- Hypotheses and selection rules were committed before the main experiments ran."
    )
    summary = results.summary
    if summary.get("test_ocr"):
        st.subheader("OCR on the held-out test split")
        st.dataframe(presentation.ocr_rows(summary), hide_index=True, width="stretch")
    if summary.get("test_matching_P0"):
        st.subheader("Name matching on the test split (baseline preprocessing)")
        st.caption(
            "FAR: decoy names accepted. FRR: true names rejected. "
            "Lower is better for both; they trade off against each other."
        )
        st.dataframe(presentation.matching_rows(summary), hide_index=True, width="stretch")
    for path, caption in results.figures:
        st.image(str(path), caption=caption)
    st.subheader("Limitations")
    st.write(
        "- One synthetic card layout and font; results do not transfer to real documents or "
        "photographs.\n"
        "- Degradations are simulated, not calibrated to real cameras.\n"
        "- One OCR engine and model set on one machine; latency is machine-specific."
    )
    st.caption(
        f"Full report: {presentation.REPORT_PATH} in the repository "
        f"({presentation.REPOSITORY_URL})."
    )


def main() -> None:
    st.set_page_config(page_title="Know Your Fan (synthetic demo)", layout="wide")
    st.title("Know Your Fan — synthetic demo")
    st.warning(SYNTHETIC_NOTICE)
    try:
        runtime = get_runtime()
    except ConfigurationError:
        _logger.error("Invalid configuration; the app will not start")
        st.error("The demo is misconfigured and cannot start. Please contact the operator.")
        st.stop()
    except StorageError as exc:
        st.error(f"The demo dataset is unavailable: {exc}")
        st.stop()
    page = st.sidebar.radio("Go to", PAGES)
    st.sidebar.caption(
        "Independent portfolio project. Not affiliated with any esports organization."
    )
    try:
        if page == "About":
            page_about()
        elif page == "Fan explorer":
            page_explorer(runtime)
        elif page == "Profile generator":
            page_generator(runtime)
        elif page == "Research":
            page_research()
        else:
            page_text_matching(runtime)
    except StorageError as exc:
        st.error(f"The demo dataset is temporarily unavailable: {exc}")
