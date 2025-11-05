#!/usr/bin/env python3
"""Fetch Poe models metadata and augment pricing with per-million-token values."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.request import urlopen

import yaml


POE_API_URL = "https://api.poe.com/v1/models"
MODELS_DEV_API_URL = "https://models.dev/api.json"
MAPPING_PATH = Path("config/model_mapping.yml")
OUTPUT_PATH = Path("dist/models.json")
MTOK_MULTIPLIER = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelMapping:
    provider: str
    model: str
    output_name: str


def fetch_json(url: str) -> Dict[str, Any]:
    """Download JSON content from a URL."""
    with urlopen(url) as response:  # nosec: B310 - API is HTTPS and trusted
        if response.status != 200:
            raise RuntimeError(f"Failed to fetch {url}: {response.status}")
        return json.load(response)


def load_poe_models() -> Dict[str, Any]:
    """Fetch the Poe models payload."""
    return fetch_json(POE_API_URL)


def load_models_dev() -> Dict[str, Any]:
    """Fetch the models.dev catalog."""
    return fetch_json(MODELS_DEV_API_URL)


def load_model_mapping(path: Path = MAPPING_PATH) -> List[ModelMapping]:
    """Load provider/model mapping configuration from YAML."""
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    entries = data.get("model_mapping", {})
    if not isinstance(entries, dict):
        raise ValueError("model_mapping config must be a mapping of output_name -> provider/model path")
    mapping: List[ModelMapping] = []
    for output_name, raw_path in entries.items():
        if not isinstance(raw_path, str) or "/" not in raw_path:
            raise ValueError(f"Invalid mapping path for {output_name!r}: {raw_path!r}")
        provider, model = raw_path.split("/", 1)
        mapping.append(ModelMapping(provider=provider, model=model, output_name=output_name))
    return mapping


def decimal_or_none(value: Any) -> Optional[Decimal]:
    """Convert a value to Decimal if possible."""
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


def normalize_pricing(pricing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Ensure pricing fields are present and add per-million-token conversions."""
    source = pricing or {}
    normalized: Dict[str, Any] = {
        "prompt": None,
        "completion": None,
        "image": source.get("image"),
        "request": source.get("request"),
        "prompt_mtok": None,
        "completion_mtok": None,
        "msrp_prompt": None,
        "msrp_completion": None,
        "msrp_prompt_mtok": None,
        "msrp_completion_mtok": None,
    }
    for key in ("prompt", "completion"):
        amount = decimal_or_none(source.get(key))
        if amount is not None:
            normalized[key] = decimal_to_string(amount)
            normalized[f"{key}_mtok"] = decimal_to_string(amount * MTOK_MULTIPLIER)
    return normalized


def build_msrp_lookup(catalog: Dict[str, Any], mapping: Sequence[ModelMapping]) -> Dict[str, Dict[str, Optional[str]]]:
    """Create a lookup of MSRP pricing keyed by output_name."""
    lookup: Dict[str, Dict[str, Optional[str]]] = {}
    for entry in mapping:
        provider_block = catalog.get(entry.provider)
        if not provider_block:
            raise KeyError(f"Provider '{entry.provider}' not found in models.dev catalog")
        model_data = provider_block.get("models", {}).get(entry.model)
        if not model_data:
            raise KeyError(f"Model '{entry.model}' not found under '{entry.provider}' in models.dev catalog")
        cost = model_data.get("cost") or {}
        prompt_mtok = decimal_or_none(cost.get("input"))
        completion_mtok = decimal_or_none(cost.get("output"))

        lookup[entry.output_name] = {
            "msrp_prompt_mtok": decimal_to_string(prompt_mtok) if prompt_mtok is not None else None,
            "msrp_completion_mtok": decimal_to_string(completion_mtok) if completion_mtok is not None else None,
            "msrp_prompt": decimal_to_string(prompt_mtok / MTOK_MULTIPLIER) if prompt_mtok is not None else None,
            "msrp_completion": decimal_to_string(completion_mtok / MTOK_MULTIPLIER) if completion_mtok is not None else None,
        }
    return lookup


def apply_msrp(pricing: Dict[str, Any], msrp_lookup: Dict[str, Dict[str, Optional[str]]], model_id: str) -> None:
    """Merge MSRP pricing into the model if available."""
    msrp_values = msrp_lookup.get(model_id)
    if not msrp_values:
        return
    pricing.update(msrp_values)


def write_output(payload: Dict[str, Any]) -> None:
    """Persist the processed payload to the dist directory."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main() -> None:
    payload = load_poe_models()
    mapping = load_model_mapping()
    models_dev_catalog = load_models_dev()
    msrp_lookup = build_msrp_lookup(models_dev_catalog, mapping)
    for model in payload.get("data", []):
        pricing = normalize_pricing(model.get("pricing"))
        apply_msrp(pricing, msrp_lookup, model.get("id"))
        model["pricing"] = pricing
    write_output(payload)


if __name__ == "__main__":
    main()
