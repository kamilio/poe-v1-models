#!/usr/bin/env python3
"""Fetch Poe models metadata, enrich pricing, and persist outputs."""

from __future__ import annotations

import json
from pathlib import Path

from poe_v1_models.pipeline import PipelineResult, run_pipeline


MODELS_OUTPUT_PATH = Path("dist/models.json")


def main() -> None:
    result = run_pipeline()
    write_models(result)


def write_models(result: PipelineResult) -> None:
    MODELS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODELS_OUTPUT_PATH.write_text(json.dumps(result.payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
