from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.request import urlopen

from poe_v1_models.pricing import PricingSnapshot, decimal_or_none
from poe_v1_models.providers.base import PricingProvider


OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


class OpenRouterProvider(PricingProvider):
    """Pricing provider backed by the OpenRouter public model catalog."""

    def __init__(self, url: str = OPENROUTER_MODELS_URL) -> None:
        super().__init__(name="openrouter")
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

        pricing = entry.get("pricing") or {}
        prompt = decimal_or_none(pricing.get("prompt"))
        completion = decimal_or_none(pricing.get("completion"))
        request = decimal_or_none(pricing.get("request"))
        image = decimal_or_none(pricing.get("image"))
        return PricingSnapshot(prompt=prompt, completion=completion, request=request, image=image)

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
