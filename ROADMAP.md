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
