from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.request import urlopen

from poe_v1_models.pricing import PricingSnapshot, decimal_or_none
from poe_v1_models.providers.base import (
    PricingProvider,
    ProviderPricingPayload,
    ProviderReportColumn,
)


OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


OPENROUTER_REPORT_COLUMNS = (
    ProviderReportColumn(key="status", label="Status", path="status"),
    ProviderReportColumn(key="reasons", label="Reasons", path="reasons"),
    ProviderReportColumn(
        key="prompt_mtok",
        label="Prompt / MTok",
        path="pricing.prompt_mtok",
        numeric=True,
    ),
    ProviderReportColumn(
        key="completion_mtok",
        label="Completion / MTok",
        path="pricing.completion_mtok",
        numeric=True,
    ),
    ProviderReportColumn(
        key="input_cache_read_mtok",
        label="Input Cache Read / MTok",
        path="pricing.input_cache_read_mtok",
        numeric=True,
    ),
    ProviderReportColumn(
        key="input_cache_write_mtok",
        label="Input Cache Write / MTok",
        path="pricing.input_cache_write_mtok",
        numeric=True,
    ),
    ProviderReportColumn(
        key="request",
        label="Request",
        path="pricing.request",
        numeric=True,
    ),
)


class OpenRouterProvider(PricingProvider):
    """Pricing provider backed by the OpenRouter public model catalog."""

    def __init__(self, url: str = OPENROUTER_MODELS_URL) -> None:
        super().__init__(name="openrouter", report_columns=OPENROUTER_REPORT_COLUMNS)
        self._url = url
        self._index: Dict[str, Mapping[str, Any]] = {}

    def load(self) -> None:
        with urlopen(self._url) as response:  # nosec: B310 - HTTPS and trusted host
            if response.status != 200:
                raise RuntimeError(f"Failed to fetch OpenRouter models: {response.status}")
            payload = json_load(response)

        data = payload.get("data")
        if not isinstance(data, Iterable):
            raise ValueError("Unexpected OpenRouter response schema: missing 'data' list")

        index: Dict[str, Mapping[str, Any]] = {}
        for entry in data:
            if isinstance(entry, Mapping):
                model_id = entry.get("id")
                if isinstance(model_id, str):
                    index[model_id] = entry
        self._index = index

    def find(self, key: str, poe_model: Mapping[str, object]) -> Optional[PricingSnapshot]:
        model_id = key
        if key == "auto":
            model_id = self.default_key(poe_model)
        if not model_id:
            return None

        entry = self._index.get(model_id)
        if entry is None:
            # Attempt loose matching using canonical slug.
            slug = slugify(model_id)
            for candidate_id, candidate_entry in self._index.items():
                candidate_slug = slugify(candidate_id)
                if candidate_slug == slug:
                    entry = candidate_entry
                    break

        if entry is None:
            return None

        payload = self.transform(entry)
        return self.build_snapshot_from_payload(payload)

    def default_key(self, poe_model: Mapping[str, object]) -> Optional[str]:
        owned_by = poe_model.get("owned_by")
        root = poe_model.get("root") or poe_model.get("id")
        if not isinstance(owned_by, str) or not isinstance(root, str):
            return None

        owned_slug = slugify(owned_by)
        root_slug = slugify(root)
        candidate = f"{owned_slug}/{root_slug}"
        if candidate in self._index:
            return candidate

        # Attempt to find a unique match by suffix.
        matches = [
            model_id
            for model_id in self._index.keys()
            if model_id.startswith(f"{owned_slug}/") and slugify(model_id.split("/", 1)[1]).startswith(root_slug)
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def transform(self, payload: Mapping[str, Any]) -> ProviderPricingPayload:
        pricing = payload.get("pricing") if isinstance(payload, Mapping) else None
        pricing_mapping: Mapping[str, Any] = pricing if isinstance(pricing, Mapping) else {}
        payload_normalized: ProviderPricingPayload = {
            "prompt": decimal_or_none(pricing_mapping.get("prompt")),
            "completion": decimal_or_none(pricing_mapping.get("completion")),
            "request": decimal_or_none(pricing_mapping.get("request")),
            "image": decimal_or_none(pricing_mapping.get("image")),
            "input_cache_read": decimal_or_none(pricing_mapping.get("input_cache_read")),
            "input_cache_write": decimal_or_none(pricing_mapping.get("input_cache_write")),
        }
        return payload_normalized


def slugify(value: str) -> str:
    """Simplistic normalisation to line up Poe identifiers with provider IDs."""
    lowered = value.lower()
    for ch in (" ", "_", ".", ":", "+"):
        lowered = lowered.replace(ch, "-")
    while "--" in lowered:
        lowered = lowered.replace("--", "-")
    return lowered


def json_load(response) -> Dict[str, Any]:
    """Helper to load a JSON payload from an HTTP response without double-reading."""
    import json

    return json.load(response)
