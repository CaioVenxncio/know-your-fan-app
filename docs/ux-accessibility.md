# UX, visual design, and accessibility (Phase 5)

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
| Text contrast | All text pairs ≥ 7.5:1 (AA needs 4.5:1) | Computed with the WCAG formula; values in `.streamlit/config.toml` |
| Non-text contrast | Pill borders `#857F75`, 3.8:1. The first version (`#C9C5BC`, 1.6:1) **failed** and was fixed | Same computation |
| Colour independence | Selected pill: fill **and** bold text. Verdicts: icon **and** wording. Chart series: colour **and** shape | Screenshots, code |
| Keyboard focus | Visible 3 px focus outline (`:focus-visible`, React Aria `data-focus-visible`). The native radio inputs stay in the DOM | `ui.py` |
| Labels | Every input has a visible label; navigation radio has an `aria-label` ("Section") | DOM inspection in Chromium |
| Charts | Axis titles and units, sample sizes in captions and tooltips, a data table under every chart | Research page |
| Headings | One header per section, with subheaders and captions in order | Screenshots |
| Mobile | Verified at 390 px: navigation fits on one row; columns stack; legends are vertical; OCR text wraps; no horizontal page overflow | Headless Chromium screenshots |

**Limits imposed by Streamlit (not fixed):**

- Charts render to canvas/SVG through Vega-Lite, so screen readers depend on the data tables.
- Tab strips scroll horizontally on narrow screens.
- Some Streamlit internals (spinners, toasts) use the framework's own markup and ARIA.
- The pill styling depends on Streamlit's DOM test ids. It was verified against Streamlit 1.65 and
  degrades to standard radio buttons if the markup changes.

No automated accessibility scanner (e.g. axe) and no screen-reader session was run. **This is not
a WCAG certification.**

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
