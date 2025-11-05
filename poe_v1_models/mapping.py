from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Optional

import yaml


MAPPING_PATH = Path("config/model_mapping.yml")


@dataclass(frozen=True)
class ModelMappingEntry:
    """Configuration describing how a Poe model maps onto pricing providers."""

    poe_id: str
    provider_keys: Mapping[str, str]

    def key_for_provider(self, provider: str) -> Optional[str]:
        """Return the provider-specific identifier for the requested provider."""
        return self.provider_keys.get(provider)

    def providers(self) -> Iterator[str]:
        return iter(self.provider_keys.keys())


def load_model_mapping(path: Path = MAPPING_PATH) -> List[ModelMappingEntry]:
    """Load Poe → provider mapping information."""
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    raw_mapping = payload.get("model_mapping")
    if not isinstance(raw_mapping, dict):
        raise ValueError("model_mapping config must be a mapping of Poe model ids to provider data")

    entries: List[ModelMappingEntry] = []
    for poe_id, value in raw_mapping.items():
        if not isinstance(poe_id, str):
            raise ValueError("model_mapping keys must be strings")
        if not isinstance(value, Mapping):
            raise ValueError(f"model_mapping value for '{poe_id}' must be a mapping of provider -> key")
        provider_keys: Dict[str, str] = {}
        for provider, key in value.items():
            if not isinstance(provider, str):
                raise ValueError(f"Provider name under '{poe_id}' must be a string")
            if not isinstance(key, str):
                raise ValueError(f"Provider mapping for '{poe_id}' and '{provider}' must be a string")
            provider_keys[provider.strip()] = key.strip()

        entries.append(ModelMappingEntry(poe_id=poe_id.strip(), provider_keys=provider_keys))

    return entries


def mapping_index(entries: Iterable[ModelMappingEntry]) -> Dict[str, ModelMappingEntry]:
    """Build a dictionary keyed by Poe model id."""
    return {entry.poe_id: entry for entry in entries}
