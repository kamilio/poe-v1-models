# Roadmap

- [x] Make clear abstractions
    - Added `poe_v1_models` package with a pricing pipeline and pluggable MSRP providers (`models.dev`, `openrouter`).
- [x] YAML config should have `key` (Poe name) and value `models.dev` => key, `openrouter` => key
    - [x] Support `auto` key so providers can infer identifiers from Poe metadata when names align.
- [x] Add general `config/config.yaml` to define provider priorities
    - [x] Exclude `-search`, `-reasoning`, and Poe-owned utility models from publications.
- [x] `config.yaml` overrides (deep merged into Poe V1 models) e.g. tagging ChatGPT variants.
- [x] Checks and report
    - Pricing checks relocated into core pipeline with rejections for conflicting providers, zero prices, and values lower than Poe's price.
    - Reports
        - [x] `checks.json` with machine-readable decisions and reason codes.
        - [x] `checks.html` visualises the JSON (yellow for blocked prices, red where Poe exceeds MSRP).
- [x] GH Pages publishing
    - Outputs generated on CI only; `dist/` is no longer tracked on `main`.
- [x] add ability to run the script locally, maybe via make
    - `make install` provisions a local virtualenv and installs runtime dependencies.
    - `make start` regenerates pricing assets and serves `dist/` via a lightweight HTTP server with direct links to key pages.
- [x] index.html
    - removed the provider dropdown in favour of an output modality filter sourced from model metadata.
- [x] report should not add new row for each provider, it should be a new columns (colspan), bascially the header is two rows. The regular things and then also the provider with subitems for all attributes.
    - models.dev pricing now respects its per-million-token units through provider-specific scaling.
    - provider columns and attribute metadata are defined in each provider, so the HTML renders columns directly from `checks.json`.
    

## Changelog
- [x] Generate changelog json, keep reading and appending to it
    - [x] Store a single snapshot of the prior run in `dist/models_previous.json` for GH Pages publication.
    - [x] Compare with the previous snapshot to append `{"date", "added", "removed", "total_models"}` entries in `dist/changelog.json`.
    - [x] Publish `dist/changelog.html` to render the changelog feed.
- [ ] Changelog inner workings
    - every `models.json` is published to GitHub Releases (timestamped version) and becomes the single source of truth; tooling only reads the most recent 30 releases.
    - the changelog generator consumes those releases via the GitHub REST API and diffs models added / removed for `dist/changelog.json`.
    - local runs hit the GitHub API (unauthenticated for public repos, optional token support if needed) so the flow can be exercised outside CI.
