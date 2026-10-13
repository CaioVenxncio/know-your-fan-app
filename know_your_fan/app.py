"""Streamlit interface for the Know Your Fan synthetic-data demonstration.

User-controlled or generated values are rendered with ``st.text``, ``st.code``
or ``st.dataframe`` and never interpolated into Markdown.
"""

from __future__ import annotations

import random

import streamlit as st

from know_your_fan.models import FanProfile
from know_your_fan.ocr import (
    OCRFailedError,
    OCRUnavailableError,
    degrade,
    extract_text,
    render_specimen,
)
from know_your_fan.storage import StorageLimitError, SyntheticProfileRepository, resolve_db_path
from know_your_fan.synthetic import GAMES, generate_profile, generate_profiles
from know_your_fan.text_matching import MAX_EXPECTED_NAME_LENGTH, match_name

SEED_DATASET_SIZE = 25
SEED_DATASET_SEED = 2025
MAX_SEARCH_LENGTH = 50
MAX_SEED = 1_000_000_000

SYNTHETIC_NOTICE = (
    "Synthetic-data demonstration. All profiles and documents are fictional. "
    "Do not enter real names, CPF numbers, addresses, or identity documents."
)
MATCHING_DISCLAIMER = "Text matching demonstration — not identity verification."

PAGES = ("About", "Fan explorer", "Profile generator", "Text-matching demo")


@st.cache_resource
def get_repository() -> SyntheticProfileRepository:
    repo = SyntheticProfileRepository(resolve_db_path())
    repo.initialize()
    repo.seed_if_empty(generate_profiles(SEED_DATASET_SIZE, seed=SEED_DATASET_SEED))
    return repo


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


def page_explorer(repo: SyntheticProfileRepository) -> None:
    st.header("Synthetic fan explorer")
    profiles = repo.list_all()
    query = st.text_input("Search name or city", max_chars=MAX_SEARCH_LENGTH).strip().casefold()
    games = st.multiselect("Filter by game", GAMES)
    filtered = [
        p
        for p in profiles
        if (not query or query in p.name.casefold() or query in p.city.casefold())
        and (not games or set(games) & set(p.interests))
    ]
    st.caption(f"{len(filtered)} of {len(profiles)} fictional profiles")
    st.dataframe(
        [
            {"Demo ID": p.demo_id, "Name": p.name, "City": p.city, "Interests": ", ".join(p.interests)}
            for p in filtered
        ],
        hide_index=True,
        width="stretch",
    )
    if filtered:
        selected = st.selectbox(
            "Profile details", filtered, format_func=lambda p: f"{p.demo_id} — {p.name}"
        )
        show_profile_details(selected)


def page_generator(repo: SyntheticProfileRepository) -> None:
    st.header("Fictional profile generator")
    st.write("Profiles are generated from a seed. There are no free-text fields, so nothing typed by a visitor is stored.")
    seed = st.number_input("Seed", min_value=0, max_value=MAX_SEED, value=0, step=1)
    if st.button("Generate profile"):
        st.session_state["generated_profile"] = generate_profile(random.Random(int(seed)))
    profile = st.session_state.get("generated_profile")
    if profile is None:
        return
    show_profile_details(profile)
    if st.button("Add to demo dataset"):
        try:
            added = repo.add(profile)
        except StorageLimitError as exc:
            st.warning(str(exc))
        else:
            if added:
                st.success("Fictional profile added to the demo dataset.")
            else:
                st.info("This profile is already in the demo dataset.")


def page_text_matching(repo: SyntheticProfileRepository) -> None:
    st.header("Text-matching demo")
    st.info(MATCHING_DISCLAIMER)
    profiles = repo.list_all()
    if not profiles:
        st.warning("The demo dataset is empty.")
        return
    profile = st.selectbox("Fictional profile", profiles, format_func=lambda p: f"{p.demo_id} — {p.name}")
    col1, col2 = st.columns(2)
    blur = col1.slider("Blur radius", 0.0, 3.0, 0.0, 0.5)
    rotation = col2.slider("Rotation (degrees)", -10, 10, 0)
    image = degrade(render_specimen(profile), blur_radius=blur, rotation_degrees=rotation)
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
            text = extract_text(image)
        result = match_name(expected, text)
    except OCRUnavailableError as exc:
        st.error(f"OCR is unavailable in this environment: {exc}")
        return
    except OCRFailedError as exc:
        st.error(f"OCR failed: {exc}")
        return
    except ValueError as exc:
        st.error(str(exc))
        return

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
    st.code(text or "(no text recognized)", language=None)


def main() -> None:
    st.set_page_config(page_title="Know Your Fan (synthetic demo)", layout="wide")
    st.title("Know Your Fan — synthetic demo")
    st.warning(SYNTHETIC_NOTICE)
    repo = get_repository()
    page = st.sidebar.radio("Go to", PAGES)
    st.sidebar.caption("Independent portfolio project. Not affiliated with any esports organization.")
    if page == "About":
        page_about()
    elif page == "Fan explorer":
        page_explorer(repo)
    elif page == "Profile generator":
        page_generator(repo)
    else:
        page_text_matching(repo)
