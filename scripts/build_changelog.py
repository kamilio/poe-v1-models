#!/usr/bin/env python3
"""Rebuild changelog artifacts from recent GitHub releases."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.changelog import build_changelog_from_snapshots
from scripts.update_models import (
    RELEASE_FETCH_LIMIT,
    fetch_release_snapshots,
    write_changelog_html,
    write_changelog_json,
)


def main() -> None:
    snapshots = fetch_release_snapshots(limit=RELEASE_FETCH_LIMIT)
    entries = build_changelog_from_snapshots(snapshots)
    write_changelog_json(entries)
    write_changelog_html()


if __name__ == "__main__":
    main()
