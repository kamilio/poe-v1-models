# Poe Models Publisher

[![Update Poe Models](https://github.com/kamilio/poe-v1-models/actions/workflows/update-models.yml/badge.svg)](https://github.com/kamilio/poe-v1-models/actions/workflows/update-models.yml)

Daily workflow that fetches model metadata from `https://api.poe.com/v1/models`, normalises pricing, evaluates multiple MSRP providers, and publishes the result (plus validation reports) to GitHub Pages.

To run the workflow on demand, click the badge above and use the **Run workflow** dropdown.

## How it works
- `scripts/update_models.py` drives the pipeline in `poe_v1_models/`, consuming Poe V1 models alongside configured MSRP providers (currently models.dev and OpenRouter).
- Provider priority, exclusion rules, and model overrides live in `config/config.yaml`. Exclusions keep house-branded/search flavours out of the published table, and overrides deep-merge into the Poe payload before publication.
- `config/model_mapping.yml` maps Poe model IDs to provider-specific identifiers. Each mapping entry may list multiple providers (`models.dev`, `openrouter`, …) and supports `auto` to infer the provider key from Poe metadata where possible.
- Generated artifacts land in `dist/` at runtime (`models.json`, `checks.json`, `checks.html`) and are uploaded to GitHub Pages via the workflow. The directory stays untracked in git.

## Local development
```bash
python3 -m pip install -r requirements.txt
python3 -m pytest
python3 scripts/update_models.py
# Inspect enrichment & validation in the terminal
python3 scripts/check_pricing.py
```

## Configuration quick reference
- `config/config.yaml` — provider priority, exclusion filters, and deep-merge overrides (e.g. tagging flagship models).
- `config/model_mapping.yml` — per-model mapping to MSRP providers. Use `auto` to let a provider infer its key from Poe metadata when the naming aligns.

## Outputs
- `dist/models.json` — Poe models with pricing normalised, per-million conversions, and validated MSRP fields.
- `dist/checks.json` — machine-readable audit of provider decisions and the checks that accepted or rejected each price.
- `dist/checks.html` — static dashboard that colours rejected prices yellow and highlights “Poe is pricier than MSRP” scenarios in red.

## Explore unmapped models
Run the interactive explorer to see which Poe models lack mappings and optionally append them to `config/model_mapping.yml`:

```bash
python3 scripts/explore_models.py --dry-run
```

Omit `--dry-run` when you are ready to write confirmed mappings. Use `--provider <name>` to limit the review to a single provider (e.g. `openai`).
