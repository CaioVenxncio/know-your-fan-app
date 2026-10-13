# UX, visual design, and accessibility (Phases 5 and 6)

## UX audit (before the redesign)

| # | Problem | Priority | Resolution |
|---|---|---|---|
| 1 | Navigation was a five-item sidebar radio, hidden behind a menu on phones; "About" was a weak entry point | High | Four sections (Home, Fans, OCR demo, Research) as a horizontal pill bar at the top; Home is the entry point |
| 2 | The synthetic-data policy was a yellow warning on every page: alarm styling for a policy note | High | Persistent "Synthetic data only" and "Not identity verification" labels plus a plain caption |
| 3 | OCR demo was an unstructured stack; bare result box; failure causes unexplained; results vanished on any rerun | High | Steps 1–3; specimen preview beside the controls; verdicts with icon and text; results persist until inputs change; research-based "why OCR misses" note |
| 4 | Profile details were dumped as monospace text; no empty state | Medium | Grouped profile card with a title; "No fictional fans match…" empty state |
| 5 | Research figures were static PNGs, unreadable on phones | Medium | Interactive charts from precomputed data, each with a data table |
| 6 | Explorer and generator were separate pages for one task | Medium | One "Fans" section with Browse and Generate tabs |
| 7 | Mixed styling, no hierarchy or identity | Medium | Theme tokens plus a small static stylesheet |

## Design system

- **Palette:**
  - warm "paper" background `#FAF9F6`, ink text `#16181D`;
  - indigo primary `#4338CA` for actions and selection;
  - restrained burnt-orange accent `#C2410C`, used only for the wordmark dot and the hero rule.
- **Charts:** an 8-colour categorical palette set in `.streamlit/config.toml`.
- **Typography:** the theme's sans-serif and monospace stacks. No web fonts are loaded, so no
  third-party requests reveal visitors.
- **Components:**
  - uppercase eyebrow labels;
  - a hero with an accent rule;
  - bordered cards;
  - numbered steps;
  - pill toggles;
  - metric tiles for verified study counts only.
- **Esports personality, kept subtle:** a scoreboard-style wordmark and pill navigation. No neon,
  gradients, logos, or third-party branding.
- **Safe rendering:** custom HTML is limited to static strings in `ui.py`. Generated or typed
  values are rendered with `st.text`, `st.code`, `st.dataframe`, or `st.metric`.

## Accessibility review (WCAG 2.2 AA principles; not a formal audit)

| Area | What was done | Evidence |
|---|---|---|
| Text contrast | Theme text pairs ≥ 7.5:1 (AA needs 4.5:1). **Correction (Phase 6):** this covered only the colours set in the theme. Colours Streamlit derives itself failed: captions 4.36:1 (faded with `opacity: .6`), the input character counter 4.4:1, and success-alert text 4.29:1. Now fixed: captions and hints #4A4E57 at full opacity (7.9:1), alert text colours set in the theme (≥ 7.9:1) | WCAG formula; axe-core scan (below) |
| Non-text contrast | Pill borders `#857F75`, 3.8:1. The first version (`#C9C5BC`, 1.6:1) **failed** and was fixed | Same computation |
| Colour independence | Selected pill: fill **and** bold text. Verdicts: icon **and** wording. Chart series: colour **and** shape | Screenshots, code |
| Keyboard focus | Visible 3 px focus outline (`:focus-visible`, React Aria `data-focus-visible`). The native radio inputs stay in the DOM | `ui.py` |
| Labels | Every input has a visible label; navigation radio has an `aria-label` ("Section") | DOM inspection in Chromium; axe-core |
| Images | The specimen card has alt text describing it (Phase 6; it had none) | axe-core |
| Landmarks | The brand bar no longer claims `role="banner"`, which duplicated Streamlit's own header (Phase 6) | axe-core |
| Charts | Axis titles and units, sample sizes in captions and tooltips, a data table under every chart | Research page |
| Headings | One `h1` per page. Home card titles were `h3` directly after the `h1` and are now `h2` (Phase 6) | axe-core, heading outline |
| Mobile | Verified at 390 px: navigation fits on one row; columns stack; legends are vertical; OCR text and profile links wrap (the links block was a horizontally scrolling region that keyboards could not reach, fixed in Phase 6); no horizontal page overflow | Headless Chromium screenshots; axe-core; `scrollWidth` check |
| Keyboard | Tab reaches the navigation, then each page's controls, with a 3 px outline on every stop; arrow keys move within the navigation | Scripted keyboard walk in Chromium (Phase 6) |

**Limits imposed by Streamlit (not fixed):**

- Charts render to canvas/SVG through Vega-Lite, so screen readers depend on the data tables.
- Tab strips scroll horizontally on narrow screens.
- Some Streamlit internals (spinners, toasts) use the framework's own markup and ARIA.
- The pill styling depends on Streamlit's DOM test ids. It was verified against Streamlit 1.65 and
  degrades to standard radio buttons if the markup changes.

## Automated scan (Phase 6)

**Tool:** axe-core 4.13.0, checked against its npm integrity hash, injected into headless Chromium
by Playwright 1.63.

**Rule sets:** `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`, `best-practice`.

**Coverage:** 23 page states at 1440 px and 390 px:
- Home;
- Fans: Browse, the empty search result, and Generate with a profile card;
- OCR demo: before running, after a match, and after the rate-limit message;
- all four Research tabs;
- the "OCR is unavailable" error, on an instance without Tesseract.

**First run:**

| Rule | Impact | Cause | Status |
|---|---|---|---|
| `color-contrast` | serious | Captions, the input character counter, and success-alert text (see above) | Fixed |
| `image-alt` | critical | Specimen card image had no alternative text | Fixed |
| `scrollable-region-focusable` | serious | Profile links block scrolled horizontally on phones | Fixed (wrapped) |
| `heading-order` | moderate | `h1` followed by `h3` on Home | Fixed |
| `landmark-no-duplicate-banner`, `landmark-unique` | moderate | Brand bar `role="banner"` plus Streamlit's header | Fixed |
| `region` | moderate (best practice) | Streamlit renders page content outside landmark elements | Not fixable in the app; framework markup |

**Final run:** 0 WCAG A/AA violations on all 23 states. One best-practice finding remains
(`region`). The run also found no browser console errors, no failed requests, and no horizontal
overflow.

**Still not done:**
- a session with a real screen reader (NVDA, VoiceOver);
- manual checks of zoom to 400 % and of text spacing;
- testing with Windows High Contrast / forced colours.

Automated tools find only part of the WCAG failures. **This is not a WCAG certification.**

## Visual validation performed

The real application was run with real Tesseract and driven in **headless Chromium** (Playwright)
at 1440×3200 and 390×3600. Screenshots covered:

- every page;
- a real OCR match;
- the Fans empty state;
- the rate-limit message;
- the Research tabs.

Issues found and fixed during that review:

1. The pill navigation CSS initially did not apply. The selectors were rewritten against the
   actual DOM.
2. The degradation chart hid half of its x-axis labels and clipped its axis title. Fixed with a
   horizontal layout.
3. The profile card truncated the demo ID.
4. On mobile, chart legends overflowed and OCR text overflowed horizontally.
5. Pill border contrast was too low (see above).

The automated tests also caught an invalid emoji icon that would have crashed the partial-match
message.

## Performance (measured on the development machine)

| Measurement | Result |
|---|---|
| Cold first script run (runtime setup, seeding 25 profiles, Home) | 2.0 s |
| Warm reruns, median of 5 | Home 9 ms, Fans 17 ms, OCR demo 26 ms (card rendering, no OCR), Research 95 ms (chart specs) |
| In-browser OCR round trip (click to result, real Tesseract) | 2.1–2.6 s |
| First page render in Chromium | 2.8–3.8 s |

Research data is parsed once per process (`st.cache_data`), and the page runs no OCR. SQLite is
read only on the Fans and OCR pages.
