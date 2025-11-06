# Poe V1 Models

Internal tooling for aggregating MSRP data for Poe's V1 model catalogue.

## Local usage

- `make install` creates a `.venv/` virtual environment and installs the runtime requirements.
- `make start` regenerates the pricing artifacts and serves the `dist/` directory locally (default `http://127.0.0.1:8000`). Override with `PORT=9000` and/or skip regeneration via `SKIP_UPDATE=1`.

Additional targets:

- `make update` refreshes the `dist/` outputs once without starting the server.
- `make changelog` rebuilds `dist/changelog.json` and `dist/changelog.html` from recent releases.
- `make release` regenerates the artifacts and publishes `models.json` as a timestamped GitHub release (requires a GitHub token with `repo` scope).
- `make test` installs dev dependencies and runs the pytest suite.

### Changelog generation

- `scripts/update_models.py` now builds `dist/changelog.json` by diffing the latest 30 GitHub releases that contain a `models.json` asset.
- Provide the repository via `POE_MODELS_RELEASES_REPOSITORY` (or rely on `GITHUB_REPOSITORY`); if unset, the tooling falls back to the `remote.origin.url` git config.
- For private repositories or higher rate limits, set `POE_MODELS_GITHUB_TOKEN`, `GH_TOKEN`, or `GITHUB_TOKEN` to authenticate GitHub API calls.
- Changelog entries include a `price_changes` section that highlights deltas for every `PricingSnapshot` field encountered across consecutive releases.
- The HTML changelog links to an RSS feed written to `dist/changelog.xml`. Configure the feed metadata via `POE_MODELS_PUBLIC_BASE_URL`, `POE_MODELS_SITE_URL`, or `PUBLIC_BASE_URL`.
