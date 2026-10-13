# Design system and UI redesign

This document records the design audit, the design system, and the decisions behind the
interface introduced on branch `design/know-your-fan-ui-redesign`. Accessibility results are in
[ux-accessibility.md](ux-accessibility.md); the navigation decision is also recorded in
[ADR 0008](decisions/0008-ui-redesign-navigation-and-theme.md).

## 1. Audit of the previous interface

The audit used screenshots and DOM measurements of the running app (Chromium, 390–1920 px).

| # | Problem | Where | Why it mattered |
|---|---|---|---|
| 1 | **Clipped wordmark.** "KNOW YOUR FAN" lost its top ~18 px whenever the app header showed toolbar items, as it does on Community Cloud. | Every page | The product name looked broken on the hosted app. Root cause in section 6. |
| 2 | **Four layers above every page.** Brand row, notice caption, pill navigation, then an uppercase label stacked above each title. | Every page | On a phone, the Home heading started at about 260 px, and the badges wrapped onto two lines. |
| 3 | **Fragile navigation.** The pill bar was a radio group restyled through Streamlit's internal test ids. | Shell | Already documented as fragile. Pages had no URLs, so a page could not be linked or bookmarked. |
| 4 | **Generic structure.** Home used three equal cards with "Open X" buttons. Uppercase, letter-spaced labels opened every section. | Home, all pages | Read as a template rather than a product, and the uppercase labels flattened the hierarchy. |
| 5 | **Explorer split from its detail.** A table, then a second select box, then a profile card below the fold. | Fans | Two controls for one task, and the result was out of view. |
| 6 | **Result far from the action.** The OCR result appeared below the image, outside a 1440×900 viewport. Tesseract's blank lines doubled the height of the text block. | OCR demo | The main outcome needed scrolling to see. |
| 7 | **Competing notices.** A blue info box and a green "final results" box sat above the research question. | Research | Two coloured boxes pulled attention before the question. |
| 8 | **Charts squashed by their legends.** Streamlit's default `autosize: fit` counts the legend inside the chart height. The τ-sweep plot was about 140 px tall, and on phones the latency scatter collapsed. Gridlines every 0.05 or 1 % added noise. | Research | Data was hard to read, especially on phones. |

## 2. Concept

The result should read as a calm, dark, editorial tool:

- typography and spacing carry the hierarchy;
- surfaces separate content by tone first, with hairline borders second;
- one lavender accent marks actions, the current page, and data series;
- status colours appear only on status messages.

Each page is shaped around its task:

| Page | Task | Layout |
|---|---|---|
| Home | Orientation | An editorial overview with actions and the study in brief |
| Fans | Browse and inspect profiles | A master–detail explorer |
| OCR demo | Run one OCR check | A two-panel workspace: specimen on one side, result on the other |
| Research | Read the evidence | A report: question, scope, findings, then the evidence tabs |

The esports theme stays in the content (games, fan activities) rather than in decoration. Nothing
on screen exists only for effect.

## 3. Tokens

Colours, fonts, radii, and heading sizes are Streamlit theme options in
`.streamlit/config.toml`. A few tokens that the theme cannot express are CSS custom properties in
`src/know_your_fan/ui.py`.

| Role | Value | Notes |
|---|---|---|
| Background | `#19191B` | App canvas |
| Surface | `#242427` | Inputs, code, table header (`secondaryBackgroundColor`) |
| Elevated | `#2B2B2F` | Panels (`st-key-panel*` containers) |
| Navigation drawer | `#1F1F22` | Phones only (`[theme.sidebar]`) |
| Text | `#F3F3F4` | 15.8:1 on the background |
| Secondary text | `#A9A9B0` | Leads, captions, labels; 7.5:1 (6.0:1 on elevated) |
| Structural line | `#34343A` | Dividers, panel borders; decorative |
| Control outline | `#6B6B73` | Inputs and selects; 3.3:1 (WCAG 1.4.11) |
| Accent | `#A99AF0` | Primary buttons, current page, links, focus ring, first data series; 7.2:1 |
| Accent, hover/press | `#BDB2F5` | Primary buttons lighten instead of darkening; 9.1:1 with dark text |
| Text on accent | `#19191B` | 7.2:1 |
| Positive / warning / negative / info text | `#81C9A2` / `#E1B77A` / `#DF8686` / `#8FB8E8` | Used only inside status messages |
| Chart series | `#A99AF0 #74C9D3 #E1B77A #DF8686 #81C9A2 #D7A6E0 #9FB3C8 #E4E4E7` | Each ≥ 6.6:1 on the background; series also differ by marker shape |

**Typography.** Local system fonts only (`system-ui`, Segoe UI, SF, Roboto…), so there are no
web-font requests. Code uses `ui-monospace`.

| Element | Size and weight |
|---|---|
| h1 | 2rem / 650 |
| h2 | 1.3rem / 600 |
| h3 | 1.05rem / 600 |
| Body | 16 px |
| Metric values | 1.6rem / 600 |
| Running text | Limited to 72ch |
| Step numbers | Tabular figures |

Uppercase is used nowhere except the specimen card itself.

**Spacing and layout.**
- Content column at most 1240 px wide.
- Streamlit's column gaps: "medium" within a section, "large" between workspaces.
- Section rhythm comes from the heading scale (h2 sections, h3 within panels).
- The main container's top padding is left to Streamlit (section 6).

**Radius.** 0.5rem for controls, buttons, and panels; the monogram uses the same value. There
are no pill shapes.

**States.**

| State | Treatment |
|---|---|
| Focus | 2 px accent outline, offset 2 px, on every interactive element |
| Hover / pressed (primary) | Lighter accent |
| Disabled | Streamlit default |
| Waiting | A spinner with a sentence ("Running OCR on the fictional card…") |
| Success, warning, error | Icon and wording, never colour alone |

## 4. Components

All components are native Streamlit APIs unless noted.

| Component | Implementation |
|---|---|
| Brand | `st.logo` with a local SVG wordmark (`assets/brand/`) |
| Navigation | `st.navigation(position="top")` with one page script per section |
| Page header | `ui.page_header`: `st.title`, a lead in secondary text, and the synthetic-data notice |
| Panels | `st.container(border=True, key="panel_…")`, styled through Streamlit's documented `st-key-*` class |
| Profile monogram | `ui.monogram`: initials only, HTML-escaped, `aria-hidden` (decorative) |
| Actions | `st.button` (secondary, or primary for the one main action on a page) |
| Data | `st.dataframe` (single-row selection on Fans), `st.metric`, Altair charts |
| Notices | `st.info`, `st.success`, `st.warning`, `st.error`, with Material icons |

Custom CSS is limited to one scoped stylesheet in `ui.py`. It uses:
- Streamlit's documented `st-key-*` classes;
- `data-testid` attributes;
- BaseWeb's `data-baseweb` attributes for control outlines.

There is no JavaScript, and there are no remote assets.

## 5. Navigation decision

Three options were built or measured:

1. **The previous radio "pill" bar.** Rejected: it relied on internal markup, had no URLs, and
   took a row of its own.
2. **`st.navigation` in the sidebar** (first iteration). It worked well visually. axe-core then
   reported `aria-allowed-attr` (critical) on every page: Streamlit's sidebar `<section>`
   carries `aria-expanded`. Fixing that in place would need DOM manipulation, which this project
   avoids.
3. **`st.navigation(position="top")`** (chosen):
   - one compact row in the app header, and the full width for content;
   - real URLs (`/fans`, `/ocr-demo`, `/research`);
   - `aria-current="page"` on the active link;
   - no axe violations on desktop or tablet.

   Below the navigation breakpoint, Streamlit moves the links into its standard drawer, which
   still carries the framework's `aria-expanded` finding (see ux-accessibility.md).

Pages are small scripts in `src/know_your_fan/page_scripts/` that call the render functions.
File pages, rather than callables, keep the selected page across reruns in the browser and in
`AppTest`, through Streamlit's public `switch_page` API.

## 6. Header clipping: root cause and fix

**Root cause.** Streamlit's app header is a 60 px, absolutely positioned bar at z-index 999990.
- When its toolbar has items, as on Community Cloud, it takes the page background and becomes
  opaque.
- When the toolbar is empty, as in local runs with `toolbarMode = "minimal"`, it is transparent.
  That is why the defect never showed locally.

The previous `ui.py` set `.block-container { padding-top: 1.6rem }`, overriding Streamlit's own
top padding, which is sized to clear that bar.

**Evidence.**
- Measured in Chromium with a populated toolbar, the wordmark spanned y = 42–76 px.
- `document.elementFromPoint` at its top edge returned `stToolbar`.
- The same result appeared at 390, 768, 1440 and 1920 px.

**Fix.**
- The override is removed, and Streamlit's padding now clears the header in every toolbar state.
- The brand moved into the header itself, through `st.logo`.
- A unit test fails if the stylesheet sets `padding-top` or a negative top margin on the main
  container.
- The browser check found no text under the header on any page, at any width, with a populated
  toolbar.

## 7. Iterations

**Iteration 1** (sidebar navigation, first dark theme). Defects observed in the rendered app:
- the synthetic-data notice floated above every H1 as an orphan line;
- profile fields in three narrow columns broke values mid-identifier ("KYF-DEMO-↵5YP9-RNT9",
  "Counter-Strike↵2");
- metric values at Streamlit's default size competed with the H1.

**Iteration 2.** The notice moved into each page header under the lead. Profile fields moved to
a two-column grid, with the demo ID on its own row. Metric values became 1.6rem. Two more fixes
followed from inspection:
- **Charts:** `autosize: fit-x` was set explicitly, so the declared height belongs to the plot.
  Fewer ticks were used (about 6 per axis). Both charts are now readable on a phone, where only
  four of eight strategy labels showed before.
- **Navigation:** moved to the top, after the axe-core finding above.
- **Primary buttons:** after a click, Streamlit's darker focus shade dropped the label to 3.5:1;
  hover, focus and press now lighten the fill instead.

Each iteration was re-checked at 390, 768, 1440 and 1920 px, and at 200 % zoom.

## 8. Remaining limitations

- The navigation drawer, on phones and at high zoom, is Streamlit markup.
- The control outline uses BaseWeb's `data-baseweb` attributes. Like any selector into
  third-party markup, it may need adjusting after a Streamlit upgrade. If it stops applying,
  controls still have a filled background and a visible label.
- On phones, the Fans table scrolls horizontally within its own grid, which is keyboard-reachable;
  the page itself does not overflow.
- On deep links such as `/research`, Streamlit's frontend first probes `/research/_stcore/…`
  (two 404s) before using the root path. This is framework behaviour, with no effect on the page.
