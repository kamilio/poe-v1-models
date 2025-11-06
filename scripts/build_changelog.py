#!/usr/bin/env python3
"""Rebuild changelog artifacts from recent GitHub releases."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.changelog import build_changelog_from_snapshots
from scripts.update_models import (
    MODELS_OUTPUT_PATH,
    RELEASE_FETCH_LIMIT,
    fetch_release_snapshots,
    write_changelog_html,
    write_changelog_json,
    write_changelog_rss,
)


def main() -> None:
    snapshots = fetch_release_snapshots(limit=RELEASE_FETCH_LIMIT)
    local_snapshot = _load_local_snapshot()
    if local_snapshot:
        snapshots = [*snapshots, local_snapshot]

    entries = build_changelog_from_snapshots(snapshots)
    write_changelog_json(entries)
    write_changelog_html()
    write_changelog_rss(entries)


def _load_local_snapshot() -> dict | None:
    if not MODELS_OUTPUT_PATH.exists():
        return None

    try:
        payload = json.loads(MODELS_OUTPUT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"Skipping local snapshot: failed to parse {MODELS_OUTPUT_PATH}: {exc}",
            file=sys.stderr,
        )
        return None

    if not isinstance(payload, dict):
        print(
            f"Skipping local snapshot: {MODELS_OUTPUT_PATH} root is not an object.",
            file=sys.stderr,
        )
        return None

    return {
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "release_tag": None,
            "release_name": "Local snapshot",
            "release_url": None,
            "source": "local",
        },
    }


if __name__ == "__main__":
    main()
