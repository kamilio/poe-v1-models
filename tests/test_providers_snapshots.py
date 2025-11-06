from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from poe_v1_models.providers.models_dev import ModelsDevProvider
from poe_v1_models.providers.openrouter import OpenRouterProvider


SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots" / "providers"


def _load_snapshot(filename: str) -> Dict[str, object]:
    path = SNAPSHOT_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def _prune_none(payload: Dict[str, str | None]) -> Dict[str, str]:
    return {key: value for key, value in payload.items() if value is not None}


def test_openrouter_transform_matches_snapshots():
    provider = OpenRouterProvider()
    data = _load_snapshot("openrouter.json")
    for record in data.get("snapshots", []):
        raw = record["raw"]
        expected = record["normalized"]
        actual = provider.build_snapshot_from_payload(provider.transform(raw)).with_mtok().as_dict()
        assert _prune_none(actual) == expected, f"Snapshot mismatch for {record.get('id')}"


def test_models_dev_transform_matches_snapshots():
    provider = ModelsDevProvider()
    data = _load_snapshot("models_dev.json")
    for record in data.get("snapshots", []):
        raw = record["raw"]
        expected = record["normalized"]
        actual = provider.build_snapshot_from_payload(provider.transform(raw)).with_mtok().as_dict()
        assert _prune_none(actual) == expected, f"Snapshot mismatch for {record.get('provider')}/{record.get('id')}"

