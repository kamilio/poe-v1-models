from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

import yaml


CONFIG_PATH = Path("config/config.yaml")


@dataclass(frozen=True)
class ProviderSettings:
    priority: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExclusionSettings:
    id_contains: List[str] = field(default_factory=list)
    id_suffixes: List[str] = field(default_factory=list)
    id_prefixes: List[str] = field(default_factory=list)
    owned_by: List[str] = field(default_factory=list)

    def should_exclude(self, poe_model: Mapping[str, Any]) -> bool:
        model_id = str(poe_model.get("id", "") or "")
        owned_by = str(poe_model.get("owned_by", "") or "")

        lowered_id = model_id.lower()
        lowered_owned = owned_by.lower()

        for prefix in self.id_prefixes:
            if lowered_id.startswith(prefix.lower()):
                return True
        for suffix in self.id_suffixes:
            if lowered_id.endswith(suffix.lower()):
                return True
        for fragment in self.id_contains:
            if fragment.lower() in lowered_id:
                return True
        for owner in self.owned_by:
            if lowered_owned == owner.lower():
                return True
        return False


@dataclass(frozen=True)
class GeneralConfig:
    providers: ProviderSettings = field(default_factory=ProviderSettings)
    exclusions: ExclusionSettings = field(default_factory=ExclusionSettings)
    overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


def load_general_config(path: Path = CONFIG_PATH) -> GeneralConfig:
    """Load the general configuration from YAML."""
    if not path.exists():
        return GeneralConfig()

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    providers_block = data.get("providers") or {}
    if not isinstance(providers_block, Mapping):
        raise ValueError("providers section must be a mapping")
    priority = providers_block.get("priority") or []
    if not isinstance(priority, list):
        raise ValueError("providers.priority must be a list")
    provider_settings = ProviderSettings(priority=[str(item).strip() for item in priority if item])

    exclusions_block = data.get("exclusions") or {}
    if not isinstance(exclusions_block, Mapping):
        raise ValueError("exclusions section must be a mapping")

    exclusions = ExclusionSettings(
        id_contains=_as_list(exclusions_block.get("id_contains")),
        id_suffixes=_as_list(exclusions_block.get("id_suffixes")),
        id_prefixes=_as_list(exclusions_block.get("id_prefixes")),
        owned_by=_as_list(exclusions_block.get("owned_by")),
    )

    overrides_block = data.get("overrides") or {}
    if not isinstance(overrides_block, Mapping):
        raise ValueError("overrides section must be a mapping of poe_id -> override mapping")
    overrides: Dict[str, Mapping[str, Any]] = {}
    for poe_id, override in overrides_block.items():
        if not isinstance(poe_id, str):
            raise ValueError("override keys must be Poe model identifiers (strings)")
        if not isinstance(override, Mapping):
            raise ValueError(f"override for '{poe_id}' must be a mapping")
        overrides[poe_id] = _sanitize_mapping(override)

    return GeneralConfig(providers=provider_settings, exclusions=exclusions, overrides=overrides)


def _as_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    raise ValueError("Expected a string or list when parsing exclusions")


def _sanitize_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Ensure nested mappings are dictionaries rather than YAML OrderedDict, etc."""
    def _convert(node: Any) -> Any:
        if isinstance(node, Mapping):
            return {str(key): _convert(val) for key, val in node.items()}
        if isinstance(node, list):
            return [_convert(item) for item in node]
        return node

    return _convert(value)
