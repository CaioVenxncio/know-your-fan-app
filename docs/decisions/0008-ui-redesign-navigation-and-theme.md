# ADR 0008: UI redesign — top navigation, file-based pages, dark theme

- **Status:** accepted
- **Date:** 2026-10-13

## Context

The previous interface had three problems:

- The radio "pill" navigation depended on internal Streamlit markup and gave pages no URLs.
- A top-padding override clipped the wordmark under Streamlit's header on Community Cloud.
- The light theme read as a default Streamlit app.

The redesign had to:

- stay within supported Streamlit APIs;
- keep every safeguard and test;
- not regress accessibility.

## Decision

1. **Navigation:** `st.navigation(position="top")`.
   - The sidebar variant was implemented and scanned first. axe-core reported
     `aria-allowed-attr` (critical) on Streamlit's sidebar `<section aria-expanded>` on every
     page, and the app cannot change that markup without DOM manipulation.
   - Top navigation has no violations on desktop and tablet. Phones get Streamlit's standard
     navigation drawer, where the finding remains (framework limitation, documented).
2. **Pages are files** (`src/know_your_fan/page_scripts/*.py`), each calling one render function.
   File pages keep the selected page across reruns in `AppTest` through the public
   `switch_page` API. Callable pages do not, because AppTest has no URL.
3. **Theme:** a dark, mostly neutral theme with one accent, set in `.streamlit/config.toml`. The
   few remaining styles go in one scoped stylesheet in `ui.py`. Fonts are local system fonts;
   there are no remote assets and no JavaScript.
4. **Layout geometry is Streamlit's.** In particular, the main container's top padding is not
   overridden. A unit test enforces this.

## Consequences

- Sections have shareable URLs (`/fans`, `/ocr-demo`, `/research`).
- The UI depends on BaseWeb's `data-baseweb` attributes only for control outlines.
- Home's primary actions use `st.switch_page`. Tests navigate with `AppTest.switch_page`, and one
  test checks both paths reach the same page.
- Details: [docs/design-system.md](../design-system.md).
