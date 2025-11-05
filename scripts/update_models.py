#!/usr/bin/env python3
"""Fetch Poe models metadata, enrich pricing, and persist outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, Optional
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.changelog import build_changelog_entry
from poe_v1_models.pipeline import PipelineResult, run_pipeline
from poe_v1_models.reporting import (
    build_checks_report,
    render_changelog_html,
    render_index_html,
    render_checks_html,
)


MODELS_OUTPUT_PATH = Path("dist/models.json")
PREVIOUS_MODELS_PATH = Path("dist/models_previous.json")
CHECKS_JSON_PATH = Path("dist/checks.json")
CHECKS_HTML_PATH = Path("dist/checks.html")
CHANGELOG_JSON_PATH = Path("dist/changelog.json")
CHANGELOG_HTML_PATH = Path("dist/changelog.html")
INDEX_HTML_PATH = Path("dist/index.html")
REMOTE_TIMEOUT = 10


def main() -> None:
    previous_payload = load_previous_payload()
    result = run_pipeline()
    write_previous_snapshot(previous_payload)
    write_models(result)
    write_checks(result)
    write_checks_html()
    write_index_html()
    update_changelog(result.payload, previous_payload)
    write_changelog_html()


def write_models(result: PipelineResult) -> None:
    MODELS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODELS_OUTPUT_PATH.write_text(
        json.dumps(result.payload, indent=2) + "\n",
        encoding="utf-8",
    )


def write_checks(result: PipelineResult) -> None:
    report = build_checks_report(result)
    CHECKS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKS_JSON_PATH.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )


def write_checks_html() -> None:
    CHECKS_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKS_HTML_PATH.write_text(render_checks_html(), encoding="utf-8")


def write_index_html() -> None:
    INDEX_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_HTML_PATH.write_text(render_index_html(), encoding="utf-8")


def write_changelog_html() -> None:
    CHANGELOG_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHANGELOG_HTML_PATH.write_text(render_changelog_html(), encoding="utf-8")


def update_changelog(
    current_payload: Dict[str, Any],
    previous_payload: Optional[Dict[str, Any]],
) -> None:
    entry = build_changelog_entry(current_payload, previous_payload)
    if previous_payload is not None and not entry["added"] and not entry["removed"]:
        return

    changelog = _load_json_if_exists(CHANGELOG_JSON_PATH)
    if changelog is None:
        changelog = []
    if not isinstance(changelog, list):
        raise RuntimeError("Changelog file is invalid; expected a list of entries.")
    changelog.append(entry)
    CHANGELOG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHANGELOG_JSON_PATH.write_text(
        json.dumps(changelog, indent=2) + "\n",
        encoding="utf-8",
    )


def write_previous_snapshot(previous_payload: Optional[Dict[str, Any]]) -> None:
    if previous_payload is None:
        return
    PREVIOUS_MODELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREVIOUS_MODELS_PATH.write_text(
        json.dumps(previous_payload, indent=2) + "\n",
        encoding="utf-8",
    )


def load_dict_if_exists(path: Path) -> Optional[Dict[str, Any]]:
    data = _load_json_if_exists(path)
    if data is None:
        return None
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return data


def _load_json_if_exists(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse JSON from {path}") from exc


def load_previous_payload() -> Optional[Dict[str, Any]]:
    local_payload = load_dict_if_exists(MODELS_OUTPUT_PATH)
    if local_payload is not None:
        return local_payload

    url = resolve_previous_models_url()
    if not url:
        return None

    remote_payload = fetch_remote_json(url)
    if remote_payload is None:
        return None
    if not isinstance(remote_payload, dict):
        raise RuntimeError(f"Unexpected payload type from {url}; expected JSON object")
    return remote_payload


def resolve_previous_models_url() -> Optional[str]:
    explicit = os.getenv("POE_MODELS_PREVIOUS_URL") or os.getenv("MODELS_PREVIOUS_URL")
    if explicit:
        return explicit
    base = os.getenv("POE_MODELS_BASE_URL")
    if base:
        return base.rstrip("/") + "/models.json"
    repository = os.getenv("GITHUB_REPOSITORY")
    if repository and "/" in repository:
        owner, repo = repository.split("/", 1)
        if owner and repo:
            return f"https://{owner}.github.io/{repo}/models.json"
    return None


def fetch_remote_json(url: str) -> Optional[Any]:
    try:
        with urlopen(url, timeout=REMOTE_TIMEOUT) as response:  # nosec: B310 - controlled URL
            if response.status != 200:
                return None
            return json.load(response)
    except (URLError, TimeoutError):
        return None


if __name__ == "__main__":
    main()
