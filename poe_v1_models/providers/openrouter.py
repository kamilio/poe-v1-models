from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.request import urlopen

from poe_v1_models.pricing import PricingSnapshot, decimal_or_none
from poe_v1_models.providers.base import (
    PricingProvider,
    ProviderPricingPayload,
    ProviderReportColumn,
)
from poe_v1_models.providers.utils import (
    canonicalize_identifier,
    is_none_mapping,
    parse_lowercase_provider_key,
    poe_identifier_candidates,
)


OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


OPENROUTER_REPORT_COLUMNS = (
    ProviderReportColumn(key="status", label="Status", path="status"),
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
                    normalized_id = model_id.strip().lower()
                    if normalized_id:
                        index[normalized_id] = entry
        self._index = index

    def find(self, key: str, poe_model: Mapping[str, object]) -> Optional[PricingSnapshot]:
        lookup_key = (key or "").strip()
        if not lookup_key:
            return None
        if is_none_mapping(lookup_key):
            return None
        if lookup_key == "auto":
            lookup_key = self.default_key(poe_model) or ""
        if not lookup_key:
            return None

        parsed = parse_lowercase_provider_key(lookup_key)
        if not parsed:
            return None

        entry = self._index.get(lookup_key)
        if entry is None:
            return None

        payload = self.transform(entry)
        return self.build_snapshot_from_payload(payload)

    def default_key(self, poe_model: Mapping[str, object]) -> Optional[str]:
        owned_by = poe_model.get("owned_by")
        identifier_candidates = poe_identifier_candidates(poe_model)
        preferred_identifier = identifier_candidates[0] if identifier_candidates else None
        if not isinstance(owned_by, str) or not preferred_identifier:
            return None

        owned_slug = owned_by.strip().lower()
        if not owned_slug:
            return None

        for identifier in identifier_candidates:
            candidate = f"{owned_slug}/{identifier}"
            if candidate in self._index:
                return candidate

        canonical_targets = {canonicalize_identifier(identifier) for identifier in identifier_candidates}
        if not canonical_targets:
            return None

        for model_id in self._index.keys():
            if not isinstance(model_id, str):
                continue
            normalized_id = model_id.strip().lower()
            if not normalized_id.startswith(f"{owned_slug}/"):
                continue
            resolved_identifier = normalized_id.split("/", 1)[1]
            if canonicalize_identifier(resolved_identifier) in canonical_targets:
                return normalized_id
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


def json_load(response) -> Dict[str, Any]:
    """Helper to load a JSON payload from an HTTP response without double-reading."""
    import json

    return json.load(response)
