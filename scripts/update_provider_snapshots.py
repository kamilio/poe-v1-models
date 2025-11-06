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


OPENROUTER_MODELS: Iterable[str] = (
    "openai/gpt-5",
    "anthropic/claude-sonnet-4.5",
    "google/gemini-2.5-pro",
)

MODELS_DEV_KEYS: Iterable[tuple[str, str]] = (
    ("openai", "gpt-5"),
    ("anthropic", "claude-sonnet-4-5"),
    ("google", "gemini-2.5-pro"),
)


def fetch_json(url: str) -> Mapping[str, object]:
    with urlopen(url) as response:  # nosec: B310 - HTTPS endpoints controlled by providers
        if response.status != 200:
            raise RuntimeError(f"Failed to fetch {url}: {response.status}")
        return json.load(response)


def normalise_values(payload: Mapping[str, str | None]) -> Mapping[str, str | None]:
    """Drop None values to keep snapshots tidy."""
    return {key: value for key, value in payload.items() if value is not None}


def update_openrouter() -> None:
    provider = OpenRouterProvider()
    payload = fetch_json(OPENROUTER_MODELS_URL)
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Unexpected OpenRouter response schema: 'data' must be a list")

    index: Dict[str, Mapping[str, object]] = {}
    for entry in data:
        if isinstance(entry, Mapping):
            model_id = entry.get("id")
            if isinstance(model_id, str):
                index[model_id] = entry

    snapshots: List[Dict[str, object]] = []
    for model_id in OPENROUTER_MODELS:
        entry = index.get(model_id)
        if entry is None:
            raise KeyError(f"Model '{model_id}' not found in OpenRouter response")

        trimmed = {
            "id": model_id,
            "pricing": entry.get("pricing") if isinstance(entry.get("pricing"), Mapping) else {},
        }
        normalized = provider.build_snapshot_from_payload(provider.transform(trimmed)).with_mtok().as_dict()
        snapshots.append(
            {
                "id": model_id,
                "raw": trimmed,
                "normalized": normalise_values(normalized),
            }
        )

    write_snapshot("openrouter.json", snapshots)


def update_models_dev() -> None:
    provider = ModelsDevProvider()
    payload = fetch_json(MODELS_DEV_API_URL)
    if not isinstance(payload, Mapping):
        raise ValueError("Unexpected models.dev response schema: payload must be a mapping")

    snapshots: List[Dict[str, object]] = []
    for provider_slug, model_name in MODELS_DEV_KEYS:
        provider_block = payload.get(provider_slug)
        if not isinstance(provider_block, Mapping):
            raise KeyError(f"Provider '{provider_slug}' not found in models.dev catalog")
        models = provider_block.get("models")
        if not isinstance(models, Mapping):
            raise ValueError(f"Provider '{provider_slug}' has no 'models' mapping")
        model_payload = models.get(model_name)
        if not isinstance(model_payload, Mapping):
            raise KeyError(f"Model '{provider_slug}/{model_name}' not found in models.dev catalog")

        trimmed = {
            "provider": provider_slug,
            "id": model_name,
            "cost": model_payload.get("cost") if isinstance(model_payload.get("cost"), Mapping) else {},
        }
        normalized = provider.build_snapshot_from_payload(provider.transform(trimmed)).with_mtok().as_dict()
        snapshots.append(
            {
                "provider": provider_slug,
                "id": model_name,
                "raw": trimmed,
                "normalized": normalise_values(normalized),
            }
        )

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
