#!/usr/bin/env python3
"""Determine whether a new models release is required."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.update_models import fetch_release_snapshots


MODELS_OUTPUT_PATH = Path("dist/models.json")


def main() -> int:
    current_models = _load_current_models(MODELS_OUTPUT_PATH)
    if current_models is None:
        print("models.json missing after generation", file=sys.stderr)
        return 1

    previous_payload = _latest_release_payload(fetch_release_snapshots(limit=1))
    release_required = True

    if previous_payload is None:
        print("No previous release detected; release will be created.")
    else:
        release_required = current_models != previous_payload
        if release_required:
            print("models.json changed relative to latest release; release will be created.")
        else:
            print("models.json unchanged relative to latest release; skipping release.")

    _write_github_output(release_required)
    return 0


def _load_current_models(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Failed to parse {path}: {exc}", file=sys.stderr)
        return None


def _latest_release_payload(
    snapshots: Sequence[Mapping[str, Any]]
) -> Optional[Mapping[str, Any]]:
    if not snapshots:
        return None
    # fetch_release_snapshots sorts snapshots by timestamp ascending
    latest = snapshots[-1]
    payload = latest.get("payload")
    if isinstance(payload, Mapping):
        return payload
    return None


def _write_github_output(release_required: bool) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"release={'true' if release_required else 'false'}\n")


if __name__ == "__main__":
    sys.exit(main())
