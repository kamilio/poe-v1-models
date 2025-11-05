# Poe Models Publisher

[![Update Poe Models](https://github.com/kamilio/poe-v1-models/actions/workflows/update-models.yml/badge.svg)](https://github.com/kamilio/poe-v1-models/actions/workflows/update-models.yml)

Daily workflow that fetches model metadata from `https://api.poe.com/v1/models`, augments pricing with per-million-token values, and publishes the result to GitHub Pages as `models.json`.

To run the workflow on demand, click the badge above and use the **Run workflow** dropdown.

## How it works
- `scripts/update_models.py` consumes the Poe API plus `https://models.dev/api.json`, normalises pricing, and enriches each model with MSRP fields (per token and per million tokens).
- Provider/model mapping lives in `config/model_mapping.yml` where keys are Poe model IDs and values point at their models.dev counterparts.
- Processed output is written to `dist/models.json`, which GitHub Pages serves.

## Local development
```bash
python3 -m pip install -r requirements.txt
python3 -m pytest
python3 scripts/update_models.py
```

## Explore unmapped models
Run the interactive explorer to see which Poe models lack mappings and optionally append them to `config/model_mapping.yml`:

```bash
python3 scripts/explore_models.py --dry-run
```

Omit `--dry-run` when you are ready to write confirmed mappings. Use `--provider <name>` to limit the review to a single provider (e.g. `openai`).
