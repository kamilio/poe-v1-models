from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional, Tuple


AUTO_MAPPING_KEY = "auto"
NONE_MAPPING_KEY = "none"


def preferred_poe_identifier(poe_model: Mapping[str, Any]) -> Optional[str]:
    """Return the primary lowercase identifier to compare against provider catalogs."""
    candidates = poe_identifier_candidates(poe_model)
    return candidates[0] if candidates else None


def poe_identifier_candidates(poe_model: Mapping[str, Any]) -> List[str]:
    """
    Return all known lowercase identifiers for the Poe model, with the Poe model ID
    taking precedence over the root for compatibility with provider catalogs.
    """
    fields: Iterable[str] = ("id", "root")
    candidates: List[str] = []
    for field in fields:
        value = poe_model.get(field)
        if not isinstance(value, str):
            continue
        lowered = value.strip().lower()
        if lowered and lowered not in candidates:
            candidates.append(lowered)
    return candidates


def canonicalize_identifier(identifier: str) -> str:
    """Normalise dotted and dashed identifiers for cross-provider comparisons."""
    return identifier.replace(".", "-")


def parse_lowercase_provider_key(key: str) -> Optional[Tuple[str, str]]:
    """Parse provider/model keys that must already be lowercase."""
    if not key or "/" not in key:
        return None
    provider, model = key.split("/", 1)
    provider = provider.strip()
    model = model.strip()
    if not provider or not model:
        return None
    if provider != provider.lower() or model != model.lower():
        return None
    return provider, model


def _normalise_special_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    lowered = value.strip().lower()
    return lowered or None


def is_auto_mapping(value: Optional[str]) -> bool:
    return _normalise_special_key(value) == AUTO_MAPPING_KEY


def is_none_mapping(value: Optional[str]) -> bool:
    return _normalise_special_key(value) == NONE_MAPPING_KEY
