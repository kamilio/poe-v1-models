#!/usr/bin/env python3
"""Download provider payloads and refresh local snapshot fixtures."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping
from urllib.request import urlopen

# Ensure the repository root is on sys.path so we can import the local package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.providers.models_dev import MODELS_DEV_API_URL, ModelsDevProvider  # noqa: E402
from poe_v1_models.providers.openrouter import OPENROUTER_MODELS_URL, OpenRouterProvider  # noqa: E402


SNAPSHOT_ROOT = ROOT / "tests" / "snapshots" / "providers"
SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)



def fetch_json(url: str) -> Mapping[str, object]:
    with urlopen(url) as response:  # nosec: B310 - HTTPS endpoints controlled by providers
        if response.status != 200:
            raise RuntimeError(f"Failed to fetch {url}: {response.status}")
        return json.load(response)


def update_openrouter() -> None:
    provider = OpenRouterProvider()
    payload = fetch_json(OPENROUTER_MODELS_URL)
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Unexpected OpenRouter response schema: 'data' must be a list")

    snapshots: List[Dict[str, object]] = []
    for entry in data:
        if not isinstance(entry, Mapping):
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str):
            continue

        raw_entry = dict(entry)
        normalized = provider.build_snapshot_from_payload(provider.transform(raw_entry)).with_mtok().as_dict()
        snapshots.append({"id": model_id, "raw": raw_entry, "normalized": normalized})

    snapshots.sort(key=lambda record: record["id"])

    write_snapshot("openrouter.json", snapshots)


def update_models_dev() -> None:
    provider = ModelsDevProvider()
    payload = fetch_json(MODELS_DEV_API_URL)
    if not isinstance(payload, Mapping):
        raise ValueError("Unexpected models.dev response schema: payload must be a mapping")

    snapshots: List[Dict[str, object]] = []
    for provider_slug, provider_block in payload.items():
        if not isinstance(provider_slug, str) or not isinstance(provider_block, Mapping):
            continue
        models = provider_block.get("models")
        if not isinstance(models, Mapping):
            continue
        for model_name, model_payload in models.items():
            if not isinstance(model_name, str) or not isinstance(model_payload, Mapping):
                continue
            raw_entry = dict(model_payload)
            normalized = provider.build_snapshot_from_payload(provider.transform(raw_entry)).with_mtok().as_dict()
            snapshots.append(
                {"provider": provider_slug, "id": model_name, "raw": raw_entry, "normalized": normalized}
            )

    snapshots.sort(key=lambda record: (record["provider"], record["id"]))

    write_snapshot("models_dev.json", snapshots)


def write_snapshot(filename: str, snapshots: List[Dict[str, object]]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": snapshots,
    }
    target = SNAPSHOT_ROOT / filename
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    update_openrouter()
    update_models_dev()
    print(f"Updated provider snapshots in {SNAPSHOT_ROOT}")  # noqa: T201 - informational output


if __name__ == "__main__":
    main()
