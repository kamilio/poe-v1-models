#!/usr/bin/env python3
"""Fetch Poe models metadata, enrich pricing, and persist outputs."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.pipeline import PipelineResult, run_pipeline
from poe_v1_models.reporting import build_checks_report, render_checks_html


MODELS_OUTPUT_PATH = Path("dist/models.json")
CHECKS_JSON_PATH = Path("dist/checks.json")
CHECKS_HTML_PATH = Path("dist/checks.html")


def main() -> None:
    result = run_pipeline()
    write_models(result)
    write_checks(result)
    write_checks_html()


def write_models(result: PipelineResult) -> None:
    MODELS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODELS_OUTPUT_PATH.write_text(json.dumps(result.payload, indent=2) + "\n", encoding="utf-8")


def write_checks(result: PipelineResult) -> None:
    report = build_checks_report(result)
    CHECKS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKS_JSON_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def write_checks_html() -> None:
    CHECKS_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKS_HTML_PATH.write_text(render_checks_html(), encoding="utf-8")


if __name__ == "__main__":
    main()
