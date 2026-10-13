"""Shared visual helpers for the Streamlit pages.

Everything rendered through ``st.markdown(..., unsafe_allow_html=True)`` here is
a **static string** defined in this module. User-controlled or generated values
are never passed to these helpers; pages render them with ``st.text``,
``st.code``, ``st.dataframe``, or ``st.metric``. As a second line of defence the
helpers HTML-escape their text arguments, so a future caller that breaks this
rule produces visible text, not markup.
"""

from __future__ import annotations

from html import escape

import streamlit as st

ACCENT = "#C2410C"
PROFILE_NAME_KEY = "profile_name"

# Static stylesheet: layout rhythm, typographic accents, and visible keyboard focus.
_CSS = """
<style>
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1180px; }
.kyf-brand { display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap;
  margin-bottom: .2rem; }
.kyf-wordmark { font-weight: 800; letter-spacing: .02em; font-size: 1.35rem; }
.kyf-wordmark span { color: #C2410C; }
.kyf-tag { font-size: .78rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: #3730A3; border: 1px solid #C7C3F4; border-radius: 999px; padding: .1rem .55rem; }
.kyf-eyebrow { font-size: .76rem; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: #3730A3; margin: 0 0 .25rem 0; }
.kyf-hero { border-left: 4px solid #C2410C; padding: .2rem 0 .2rem 1rem; margin: .6rem 0 1.2rem 0; }
.kyf-hero h1 { font-size: 2.3rem; line-height: 1.15; margin: 0 0 .5rem 0; padding: 0; }
.kyf-hero p { font-size: 1.08rem; max-width: 46rem; margin: 0; color: #2B2E36; }
.kyf-step { display: inline-flex; align-items: center; justify-content: center; width: 1.6rem;
  height: 1.6rem; border-radius: 999px; background: #4338CA; color: #FFFFFF; font-weight: 700;
  font-size: .85rem; margin-right: .5rem; }
.kyf-step-title { font-weight: 700; font-size: 1.05rem; }
.kyf-muted { color: #4A4E57; font-size: .92rem; }
:focus-visible { outline: 3px solid #4338CA !important; outline-offset: 2px !important; }
/* Horizontal radio groups (navigation, metric toggles) styled as pills. Uses Streamlit's stable
   test ids and React Aria's data attributes (verified against Streamlit 1.65's DOM). The native
   radio input stays in the DOM for keyboard and screen-reader use; the selected pill is shown by
   fill and bold text, not by colour alone. */
[data-testid="stRadioGroup"][aria-orientation="horizontal"] { gap: .45rem; flex-wrap: wrap; }
[aria-orientation="horizontal"] [data-testid="stRadioOption"] { border: 1px solid #857F75;
  border-radius: 999px; padding: .3rem .95rem; background: #FFFFFF; margin: 0 !important; }
[aria-orientation="horizontal"] [data-testid="stRadioOption"] > div > div:first-child {
  display: none; }
[aria-orientation="horizontal"] [data-testid="stRadioOption"][data-selected="true"] {
  background: #4338CA; border-color: #4338CA; }
[aria-orientation="horizontal"] [data-testid="stRadioOption"][data-selected="true"] p {
  color: #FFFFFF; font-weight: 700; }
[data-testid="stRadioOption"][data-focus-visible="true"],
[data-testid="stRadioOption"]:has(input:focus-visible) { outline: 3px solid #4338CA;
  outline-offset: 2px; }
/* Streamlit fades captions (opacity .6) and input hints to about 4.4:1, below WCAG AA.
   Solid #4A4E57 instead: 7.9:1 on the page, 7.2:1 on the secondary background. */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
[data-testid="InputInstructions"] { color: #4A4E57; opacity: 1; }
/* Home card titles are h2 (heading order) at the visual size of a subheader. */
[class*="st-key-home_card_"] h2 { font-size: 1.5rem; padding-top: .25rem; }
/* Profile card title: the fictional name, rendered as plain text inside a keyed container. */
[class*="st-key-profile_name_"] [data-testid="stText"] { font-size: 1.45rem; font-weight: 700; }
@media (max-width: 640px) {
  .kyf-hero h1 { font-size: 1.75rem; }
  .kyf-hero p { font-size: 1rem; }
}
</style>
"""

_BRAND = """
<div class="kyf-brand">
  <span class="kyf-wordmark">KNOW YOUR FAN<span>.</span></span>
  <span class="kyf-tag">Synthetic data only</span>
  <span class="kyf-tag">Not identity verification</span>
</div>
"""


def apply_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def brand_bar() -> None:
    st.markdown(_BRAND, unsafe_allow_html=True)


def eyebrow(label: str) -> None:
    """Small uppercase section label. ``label`` must be a static string."""
    st.markdown(f'<p class="kyf-eyebrow">{escape(label)}</p>', unsafe_allow_html=True)


def hero(title: str, lead: str) -> None:
    """Page hero. ``title`` and ``lead`` must be static strings."""
    st.markdown(
        f'<div class="kyf-hero"><h1>{escape(title)}</h1><p>{escape(lead)}</p></div>',
        unsafe_allow_html=True,
    )


def step(number: int, title: str) -> None:
    """Numbered step heading. ``title`` must be a static string."""
    st.markdown(
        f'<span class="kyf-step" aria-hidden="true">{int(number)}</span>'
        f'<span class="kyf-step-title">Step {int(number)}: {escape(title)}</span>',
        unsafe_allow_html=True,
    )
