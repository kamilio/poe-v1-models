from __future__ import annotations

from typing import Any, Dict, Mapping, Optional
from urllib.request import urlopen

from poe_v1_models.pricing import PricingSnapshot, decimal_or_none
from poe_v1_models.providers.base import PricingProvider, ProviderReportColumn


MODELS_DEV_API_URL = "https://models.dev/api.json"


MODELS_DEV_REPORT_COLUMNS = (
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
        lookup_key = key
        if not lookup_key or lookup_key == "auto" or "/" not in lookup_key:
            lookup_key = self.default_key(poe_model)
        if not lookup_key or "/" not in lookup_key:
            return None
        provider, model = lookup_key.split("/", 1)
        provider_block = self._catalog.get(provider)
        if not provider_block:
            return None
        models = provider_block.get("models", {})
        model_data = models.get(model)
        if not model_data:
            slug = slugify(model)
            for candidate, candidate_data in models.items():
                if slugify(candidate) == slug:
                    model_data = candidate_data
                    break
        if not model_data:
            return None
        cost = model_data.get("cost") or {}
        prompt = decimal_or_none(cost.get("input"))
        completion = decimal_or_none(cost.get("output"))
        request = decimal_or_none(cost.get("request") or cost.get("cache_read"))
        image = decimal_or_none(cost.get("image"))
        return self.build_snapshot(prompt=prompt, completion=completion, request=request, image=image)

    def default_key(self, poe_model: Mapping[str, object]) -> Optional[str]:
        owned_by = poe_model.get("owned_by")
        root = poe_model.get("root") or poe_model.get("id")
        if not isinstance(owned_by, str) or not isinstance(root, str):
            return None

        provider_slug = slugify(owned_by)
        provider_block = self._catalog.get(provider_slug)
        if not isinstance(provider_block, Mapping):
            return None

        models = provider_block.get("models")
        if not isinstance(models, Mapping):
            return None

        root_slug = slugify(root)
        if root_slug in models:
            return f"{provider_slug}/{root_slug}"

        exact_match = None
        prefix_matches = []
        for candidate in models.keys():
            candidate_slug = slugify(candidate)
            if candidate_slug == root_slug:
                exact_match = candidate
                break
            if candidate_slug.startswith(root_slug) or root_slug.startswith(candidate_slug):
                prefix_matches.append(candidate)

        if exact_match:
            return f"{provider_slug}/{exact_match}"

        if len(prefix_matches) == 1:
            return f"{provider_slug}/{prefix_matches[0]}"
        return None


def json_load(response) -> Dict[str, Any]:
    """Helper to load a JSON payload from an HTTP response without double-reading."""
    import json

    return json.load(response)


def slugify(value: str) -> str:
    """Mirror OpenRouter slug normalisation to align catalogue identifiers."""
    lowered = value.lower()
    for ch in (" ", "_", ".", ":", "+"):
        lowered = lowered.replace(ch, "-")
    while "--" in lowered:
        lowered = lowered.replace("--", "-")
    return lowered
