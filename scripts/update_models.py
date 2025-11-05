#!/usr/bin/env python3
"""Fetch Poe models metadata and augment pricing with per-million-token values."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import urlopen


API_URL = "https://api.poe.com/v1/models"
OUTPUT_PATH = Path("dist/models.json")
MTOK_MULTIPLIER = Decimal(1_000_000)


def fetch_models() -> Dict[str, Any]:
    """Download the latest models payload from Poe."""
    with urlopen(API_URL) as response:  # nosec: B310 - API is HTTPS and trusted
        if response.status != 200:
            raise RuntimeError(f"Failed to fetch models: {response.status}")
        return json.load(response)


def parse_decimal(value: Any) -> Optional[Decimal]:
    """Convert a JSON pricing string into a Decimal, or return None if invalid."""
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def decimal_to_string(value: Decimal) -> str:
    """Format Decimal without scientific notation or trailing zeros."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def enrich_pricing(pricing: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Add per-million-token pricing fields when prompt or completion prices exist."""
    if not pricing:
        return pricing

    augmented = dict(pricing)
    for key in ("prompt", "completion"):
        amount = parse_decimal(augmented.get(key))
        if amount is None:
            continue
        per_million = amount * MTOK_MULTIPLIER
        augmented[f"{key}_mtok"] = decimal_to_string(per_million)
    return augmented


def write_output(payload: Dict[str, Any]) -> None:
    """Persist the processed payload to the dist directory."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main() -> None:
    payload = fetch_models()
    for model in payload.get("data", []):
        model["pricing"] = enrich_pricing(model.get("pricing"))
    write_output(payload)


if __name__ == "__main__":
    main()
