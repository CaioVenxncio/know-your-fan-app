# Privacy Statement

**Know Your Fan is an independent demonstration project that works only with synthetic data.**

- **What the app asks for:** nothing personal. It has no registration form, no accounts, no file
  uploads, and no fields for names, CPF numbers, addresses, or identity documents of real people.
- **What is stored:** only fictional profiles produced by the built-in generator, kept in a
  SQLite file on the machine running the app.
- **What you type:** the search box and the "name to look for" field are length-limited. Their
  values stay in the server's memory for your browser session (so a result can stay on screen) and
  are never written to the database or to logs.
- **Browser storage:** Streamlit sets one technical cookie (`_streamlit_xsrf`, cross-site request
  forgery protection) and remembers the colour theme in local storage. There are no tracking
  cookies, and the pages load no third-party resources (checked in a browser in Phase 6).
- **Analytics:** Streamlit usage statistics are disabled in `.streamlit/config.toml`, and the app
  sends no telemetry of its own.
- **Logs:** application logs record technical events only (for example "rate limit reached"),
  never typed text, names, OCR output, or profile data.
- **Hosting:** if the app is hosted, the hosting platform and network operators can still see and
  log standard connection metadata, such as IP addresses, request times, and browser user agents.
  That is outside the app's control and is covered by the host's own privacy terms.
- **Your responsibility:** do not type real personal information into any field. Any name that
  resembles a real person is coincidental.

Questions can be raised through the repository's issue tracker. Please do not include personal data.
