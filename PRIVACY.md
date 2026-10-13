# Privacy Statement

**Know Your Fan is an independent demonstration project that works only with synthetic data.**

## What the app does

- **What the app asks for:** nothing personal. It has no registration form, no accounts, no file
  uploads, and no fields for names, CPF numbers, addresses, or identity documents of real people.
- **What is stored:** only fictional profiles produced by the built-in generator, kept in a
  SQLite file on the server running the app. This file may be reset whenever the app restarts.
- **What you type:** the search box and the "name to look for" field are length-limited. Their
  values stay in the server's memory for your browser session, so a result can stay on screen.
  They are never written to the database or to logs.
- **Processing:** all OCR runs on the server, on card images the app draws itself. Nothing is sent
  to third-party services by the app.
- **Logs:** application logs record technical events only, for example "rate limit reached".
  They never contain typed text, names, OCR output, or profile data.
- **Your responsibility:** do not type real personal information into any field. Any name that
  resembles a real person is coincidental.

## Running it yourself (local or Docker)

- Streamlit usage statistics are disabled in `.streamlit/config.toml`.
- Streamlit sets one technical cookie (`_streamlit_xsrf`, which protects against cross-site
  request forgery).
- The colour theme is remembered in your browser's local storage.
- The pages load no third-party resources (checked in a browser in Phase 6).

## If the app is hosted (for example on Streamlit Community Cloud)

The hosting platform runs the app and has its own privacy terms, which apply in addition to this
statement. It is outside this project's control. Based on the platform's documentation and
responses observed from a Community Cloud app:

- **Usage statistics:** Community Cloud enforces `browser.gatherUsageStats = true`, which
  overrides this project's setting. With that setting, the Streamlit page in your browser contacts
  Streamlit's telemetry services. In a local test with the same setting, it requested
  `data.streamlit.io` and `webhooks.fivetran.com`. What is collected is governed by Streamlit's
  and Snowflake's privacy terms, not by this project.
- **Cookies:** the platform sets its own HttpOnly, Secure cookies, including a session cookie, a
  CSRF cookie, and a `proxy-tracking-id` cookie that lasts about 31 days.
- **Connection metadata:** like any host, the platform and network operators can see and log
  connection metadata, such as IP addresses, request times, and browser user agents.

Questions can be raised through the repository's issue tracker. Please do not include personal data.
