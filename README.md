# Poe V1 Models

Internal tooling for aggregating MSRP data for Poe's V1 model catalogue.

## Local usage

- `make install` creates a `.venv/` virtual environment and installs the runtime requirements.
- `make start` regenerates the pricing artifacts and serves the `dist/` directory locally (default `http://127.0.0.1:8000`). Override with `PORT=9000` and/or skip regeneration via `SKIP_UPDATE=1`.

Additional targets:

- `make update` refreshes the `dist/` outputs once without starting the server.
- `make test` installs dev dependencies and runs the pytest suite.
