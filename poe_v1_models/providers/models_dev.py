from __future__ import annotations

from typing import Any, Dict, Mapping, Optional
from urllib.request import urlopen

from poe_v1_models.pricing import PricingSnapshot, decimal_or_none
from poe_v1_models.providers.base import PricingProvider


MODELS_DEV_API_URL = "https://models.dev/api.json"


class ModelsDevProvider(PricingProvider):
    """Pricing provider reading MSRP data from models.dev."""

    def __init__(self, url: str = MODELS_DEV_API_URL) -> None:
        super().__init__(name="models.dev")
        self._url = url
        self._catalog: Dict[str, Any] = {}

    def load(self) -> None:
        with urlopen(self._url) as response:  # nosec: B310 - HTTPS and trusted host
            if response.status != 200:
                raise RuntimeError(f"Failed to fetch models.dev catalog: {response.status}")
            self._catalog = json_load(response)

    def find(self, key: str, poe_model: Mapping[str, object]) -> Optional[PricingSnapshot]:
        if not key or "/" not in key:
            return None
        provider, model = key.split("/", 1)
        provider_block = self._catalog.get(provider)
        if not provider_block:
            return None
        model_data = provider_block.get("models", {}).get(model)
        if not model_data:
            return None
        cost = model_data.get("cost") or {}
        prompt = decimal_or_none(cost.get("input"))
        completion = decimal_or_none(cost.get("output"))
        request = decimal_or_none(cost.get("request"))
        image = decimal_or_none(cost.get("image"))
        return PricingSnapshot(prompt=prompt, completion=completion, request=request, image=image)


def json_load(response) -> Dict[str, Any]:
    """Helper to load a JSON payload from an HTTP response without double-reading."""
    import json

    return json.load(response)
