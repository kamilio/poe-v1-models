from __future__ import annotations

from typing import Any, Dict, Mapping, Optional
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


MODELS_DEV_API_URL = "https://models.dev/api.json"


MODELS_DEV_REPORT_COLUMNS = (
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
)


class ModelsDevProvider(PricingProvider):
    """Pricing provider reading MSRP data from models.dev."""

    def __init__(self, url: str = MODELS_DEV_API_URL) -> None:
        super().__init__(
            name="models.dev",
            token_unit="per_million",
            report_columns=MODELS_DEV_REPORT_COLUMNS,
        )
        self._url = url
        self._catalog: Dict[str, Any] = {}

    def load(self) -> None:
        with urlopen(self._url) as response:  # nosec: B310 - HTTPS and trusted host
            if response.status != 200:
                raise RuntimeError(f"Failed to fetch models.dev catalog: {response.status}")
            self._catalog = json_load(response)

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
        provider, model = parsed
        provider_block = self._catalog.get(provider)
        if not provider_block:
            return None
        models = provider_block.get("models", {})
        model_data = models.get(model)
        if not model_data:
            return None
        payload = self.transform(model_data)
        return self.build_snapshot_from_payload(payload)

    def default_key(self, poe_model: Mapping[str, object]) -> Optional[str]:
        owned_by = poe_model.get("owned_by")
        identifier_candidates = poe_identifier_candidates(poe_model)
        preferred_identifier = identifier_candidates[0] if identifier_candidates else None
        if not isinstance(owned_by, str) or not preferred_identifier:
            return None

        provider_slug = owned_by.strip().lower()
        if not provider_slug:
            return None

        provider_block = self._catalog.get(provider_slug)
        if not isinstance(provider_block, Mapping):
            return None

        models = provider_block.get("models")
        if not isinstance(models, Mapping):
            return None

        for identifier in identifier_candidates:
            if identifier in models:
                return f"{provider_slug}/{identifier}"

        canonical_targets = {canonicalize_identifier(identifier) for identifier in identifier_candidates}
        if not canonical_targets:
            return None

        for model_name in models.keys():
            if not isinstance(model_name, str):
                continue
            normalized_model = model_name.strip().lower()
            if canonicalize_identifier(normalized_model) in canonical_targets:
                return f"{provider_slug}/{normalized_model}"
        return None

    def transform(self, payload: Mapping[str, Any]) -> ProviderPricingPayload:
        cost = payload.get("cost") if isinstance(payload, Mapping) else None
        cost_mapping: Mapping[str, Any] = cost if isinstance(cost, Mapping) else {}
        payload_normalized: ProviderPricingPayload = {
            "prompt": decimal_or_none(cost_mapping.get("input")),
            "completion": decimal_or_none(cost_mapping.get("output")),
            "request": decimal_or_none(cost_mapping.get("request")),
            "image": decimal_or_none(cost_mapping.get("image")),
            "input_cache_read": decimal_or_none(cost_mapping.get("cache_read")),
            "input_cache_write": decimal_or_none(cost_mapping.get("cache_write")),
        }
        return payload_normalized


def json_load(response) -> Dict[str, Any]:
    """Helper to load a JSON payload from an HTTP response without double-reading."""
    import json

    return json.load(response)
