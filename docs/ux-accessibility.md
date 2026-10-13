# UX and accessibility

The current interface comes from the UI redesign (branch `design/know-your-fan-ui-redesign`). Its
audit, tokens, and decisions are in [design-system.md](design-system.md). This page records how
accessibility was checked, what was found, and what is still open. The sections at the end keep
the earlier Phase 5 and Phase 6 findings for the record.

## Accessibility review (WCAG 2.2 A/AA principles; not a formal audit)

| Area | Current state | Evidence |
|---|---|---|
| Text contrast | Text 15.8:1, secondary text 7.5:1 (6.0:1 on panels), accent 7.2:1, status text ≥ 6.6:1. Streamlit fades captions with `opacity: .6`; `ui.py` restores full opacity | WCAG formula; axe-core |
| Primary buttons | Dark label on the accent, 7.2:1. Streamlit darkens the fill on focus, which gave 3.5:1 after a click; hover, focus and press now lighten it (9.1:1) | axe-core found the focus state; fixed |
| Non-text contrast | Text inputs and selects have a `#6B6B73` outline, 3.3:1 against the page | WCAG formula |
| Colour independence | Current page: fill **and** `aria-current="page"`. Verdicts: icon **and** wording. Chart series: colour **and** marker shape | Screenshots, DOM |
| Keyboard | Tab order: navigation links, header toolbar, then page controls in reading order. Every stop shows a 2 px accent outline. Enter on a navigation link opens the page | Scripted keyboard walk in Chromium |
| Labels and names | Every input has a visible label. Navigation entries are links with their page names. The specimen image has alt text. The profile monogram is `aria-hidden`, because the name is shown as text next to it | axe-core, DOM |
| Headings | One `h1` per page; sections `h2`; panel titles `h3` | Heading outline from the DOM |
| Charts | Axis titles with units, sample sizes in captions and tooltips, a data table under every chart. Charts keep their declared plot height (`autosize: fit-x`), so legends no longer squeeze them on phones | Research page at 390–1920 px |
| Responsive | 390, 768, 1440, 1920 px and 200 % zoom: no horizontal page overflow, columns stack, and no text sits under the app header | `scrollWidth` and header-overlap checks in Chromium |

## Automated scan

**Tool:** axe-core 4.13.0, checked against its npm integrity hash, injected into headless Chromium
by Playwright 1.63.

**Rule sets:** `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, `best-practice`.

**Coverage:** 39 page states:

| Viewport | States scanned |
|---|---|
| 390, 768, 1440, 1920 px | Home; Fans; OCR demo; all four Research tabs |
| 1440 px only | The Fans empty search result; Generate with a profile; the "OCR is unavailable" error, on an instance without Tesseract |
| 390 and 1440 px | OCR demo after a match, and after the rate-limit message |
| 200 % zoom | All four pages |

**Results:**

| Rule | Impact | Where | Status |
|---|---|---|---|
| `color-contrast` | serious | Primary button after a click (Streamlit's darker focus shade) | Fixed |
| `aria-allowed-attr` | critical | Sidebar navigation: Streamlit's `<section aria-expanded>` on every page | Avoided on desktop and tablet by moving the navigation to the top |
| `aria-allowed-attr` | critical | The same element in Streamlit's navigation drawer, at 390 px and 200 % zoom | **Open: framework markup**, not changeable without DOM manipulation |
| `region` | moderate (best practice) | Streamlit renders content outside landmark elements | Open: framework markup |

**Final state:** 0 WCAG A/AA violations at 768, 1440, and 1920 px. At 390 px and 200 % zoom the
only finding is the framework's drawer attribute above.

**Other checks in the same run:**
- no browser console errors other than Streamlit's base-path probes on deep links (404s);
- no requests to any origin other than the app;
- no horizontal overflow.

**Still not done:**
- a session with a real screen reader (NVDA, VoiceOver);
- zoom to 400 %;
- text-spacing overrides;
- Windows High Contrast / forced colours.

Automated tools find only part of the WCAG failures. **This is not a WCAG certification.**

## Functional checks in the browser (redesign)

| Check | Result |
|---|---|
| OCR demo with real Tesseract, session limit set to 3 | Three matches, then the rate-limit message, at 390 and 1440 px |
| Fans empty state | Shown for an unmatched search |
| Selecting a table row | Opens that profile in the panel |
| Generate tab | Previews a generated profile |
| Instance without Tesseract | "OCR is unavailable in this environment." with no details; the server log has the fixed message only |
| Header | With a populated toolbar (as on Community Cloud), no page title or text is under the header at any tested width |

## Limits imposed by Streamlit

- The navigation drawer on narrow screens carries `aria-expanded` on a `<section>` (above).
- Charts render through Vega-Lite, so screen-reader users rely on the data tables.
- Data grids and tab strips scroll horizontally inside their own region on narrow screens.
- Spinners and toasts use the framework's own markup.
- Control outlines use BaseWeb's `data-baseweb` attributes and may need checking after a
  Streamlit upgrade.

## History

**Phase 5 (light theme, pill navigation).**
- The first browser review fixed: pill CSS that did not apply, hidden axis labels, a truncated
  demo ID, mobile overflow, and pill borders at 1.6:1.
- Phase 5 claimed every text pair was at least 7.5:1. That covered only theme colours, and was
  corrected in Phase 6.

**Phase 6 (axe-core, 23 states).** Fixed:
- contrast of Streamlit-derived colours (captions 4.36:1, success text 4.29:1);
- the missing alt text on the specimen image;
- an unreachable scroll region;
- heading order;
- a duplicate banner landmark.

The final Phase 6 run had 0 WCAG A/AA violations.

**Performance** (Phase 5, development machine):

| Measurement | Result |
|---|---|
| Cold first script run | 2.0 s |
| Warm reruns | 9–95 ms |
| In-browser OCR round trip | 2.1–2.6 s |

The research data is parsed once per process, and the Research page runs no OCR.
