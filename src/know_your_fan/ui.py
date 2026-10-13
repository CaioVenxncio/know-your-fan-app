"""Design system helpers for the Streamlit pages (see docs/design-system.md).

Colours, fonts, radii and heading sizes are theme tokens in `.streamlit/config.toml`.
This module adds what the theme cannot express: a small scoped stylesheet, brand
assets, and a few layout helpers.

Rendering policy: everything passed to ``st.markdown(..., unsafe_allow_html=True)``
here is either a static string defined in this module or text escaped with
:func:`html.escape`. Pages render user-controlled and generated values with
``st.text``, ``st.code``, ``st.dataframe`` or ``st.metric``; the only generated value
used here is a profile's initials in :func:`monogram`, which are letters only and
escaped. A test fails if any other module emits raw HTML.
"""

from __future__ import annotations

from html import escape
from importlib import resources
from pathlib import Path

import streamlit as st

SYNTHETIC_NOTICE = (
    "Synthetic-data demonstration. All profiles and documents are fictional. "
    "Do not enter real names, CPF numbers, addresses, or identity documents."
)
PANEL_KEY = "panel"
PROFILE_NAME_KEY = "profile_name"

_BRAND = resources.files("know_your_fan").joinpath("assets/brand")

# Scoped stylesheet. Selectors use Streamlit's documented `st-key-<key>` classes for
# keyed containers, stable `data-testid` attributes, and BaseWeb's `data-baseweb`
# attributes for form controls. Nothing here changes layout geometry that Streamlit
# relies on: in particular the main container's top padding is left to Streamlit,
# because it reserves the space under the fixed app header (see docs/design-system.md,
# "Header clipping").
_CSS = """
<style>
:root {
  --kyf-surface: #242427; --kyf-elevated: #2B2B2F; --kyf-line: #34343A;
  --kyf-control-line: #6B6B73; --kyf-text-2: #A9A9B0; --kyf-accent: #A99AF0;
  --kyf-on-accent: #19191B; --kyf-accent-hover: #BDB2F5;
}
[data-testid="stMainBlockContainer"] { max-width: 1240px; padding-bottom: 3rem; }
/* Readable measure for running text. */
[data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] p { max-width: 72ch; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
  color: var(--kyf-text-2); opacity: 1; }
/* Panels: tonal separation first, a hairline second. */
[class*="st-key-panel"] { background: var(--kyf-elevated); border-color: var(--kyf-line); }
/* Form controls need a 3:1 boundary (WCAG 1.4.11); structural lines stay subtle. */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"],
[data-testid="stNumberInputContainer"] { border-color: var(--kyf-control-line) !important; }
/* Primary buttons: dark text on the light accent (7.2:1). Streamlit darkens the fill on
   hover, focus and press (to #6E56E6, 3.5:1 with dark text); on this dark theme those states
   lighten instead, keeping the label at >= 7:1. */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primary"] p {
  color: var(--kyf-on-accent); font-weight: 600; }
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primary"]:focus,
[data-testid="stBaseButton-primary"]:focus-visible, [data-testid="stBaseButton-primary"]:active {
  background-color: var(--kyf-accent-hover); border-color: var(--kyf-accent-hover);
  color: var(--kyf-on-accent); }
:focus-visible { outline: 2px solid var(--kyf-accent) !important; outline-offset: 2px !important; }
/* Monogram for a fictional profile (initials only). */
.kyf-monogram { display: inline-flex; align-items: center; justify-content: center;
  width: 2.75rem; height: 2.75rem; border-radius: 0.5rem; background: var(--kyf-surface);
  border: 1px solid var(--kyf-line); color: var(--kyf-accent); font-weight: 650;
  letter-spacing: .02em; }
[class*="st-key-profile_name"] [data-testid="stText"] { font-size: 1.3rem; font-weight: 650;
  line-height: 1.3; }
/* Step numbers on Home: tabular figures in the accent colour. */
.kyf-step-no { font-variant-numeric: tabular-nums; color: var(--kyf-accent); font-weight: 650;
  font-size: .85rem; letter-spacing: .04em; margin: 0 0 .25rem 0; }
</style>
"""


def apply_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def brand_assets() -> tuple[Path, Path]:
    """Wordmark and compact mark (local SVG files) for ``st.logo``."""
    return (
        Path(str(_BRAND.joinpath("wordmark.svg"))),
        Path(str(_BRAND.joinpath("mark.svg"))),
    )


def page_header(title: str, lead: str) -> None:
    """Page title (h1), a short lead, and the synthetic-data notice (on every page)."""
    st.title(title, anchor=False)
    st.markdown(f":gray[{lead}]")
    st.caption(SYNTHETIC_NOTICE)


def step_number(number: int) -> None:
    st.markdown(f'<p class="kyf-step-no">{int(number):02d}</p>', unsafe_allow_html=True)


def initials(name: str) -> str:
    """Up to two initials, letters only (first and last word)."""
    words = [w for w in name.split() if w[:1].isalpha()]
    if not words:
        return ""
    picked = words[:1] + words[-1:] if len(words) > 1 else words
    return "".join(w[0] for w in picked).upper()


def monogram(name: str) -> None:
    """Typographic avatar for a fictional profile. Decorative: hidden from screen readers."""
    st.markdown(
        f'<span class="kyf-monogram" aria-hidden="true">{escape(initials(name))}</span>',
        unsafe_allow_html=True,
    )
