from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml


CONFIG_PATH = Path("config/config.yaml")


@dataclass(frozen=True)
class ProviderSettings:
    priority: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExclusionRule:
    kind: str
    value: str
    reason: Optional[str] = None

    def matches(self, poe_model: Mapping[str, Any]) -> bool:
        candidate: Optional[str] = None
        if self.kind == "id":
            candidate = str(poe_model.get("id", "") or "")
        elif self.kind == "owner":
            candidate = str(poe_model.get("owned_by", "") or "")

        if candidate is None:
            return False

        return candidate.strip().lower() == self.value.strip().lower()


@dataclass(frozen=True)
class ExclusionSettings:
    rules: List[ExclusionRule] = field(default_factory=list)

    def should_exclude(self, poe_model: Mapping[str, Any]) -> bool:
        return self.rule_for(poe_model) is not None

    def rule_for(self, poe_model: Mapping[str, Any]) -> Optional[ExclusionRule]:
        for rule in self.rules:
            if rule.matches(poe_model):
                return rule
        return None


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

    raw_exclusions = data.get("exclusions")
    if raw_exclusions is None and "exclusion" in data:
        raw_exclusions = data.get("exclusion")
    exclusions = ExclusionSettings(rules=_parse_exclusion_rules(raw_exclusions))

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


def _parse_exclusion_rules(raw: Any) -> List[ExclusionRule]:
    if raw is None:
        return []

    if isinstance(raw, list):
        return [_parse_exclusion_rule(item) for item in raw]

    if isinstance(raw, Mapping):
        rules: List[ExclusionRule] = []
        for model_id in _as_list(raw.get("ids")):
            rules.append(ExclusionRule(kind="id", value=model_id))
        owner_keys = raw.get("owners") or raw.get("owned_by")
        for owner in _as_list(owner_keys):
            rules.append(ExclusionRule(kind="owner", value=owner))
        return rules

    raise ValueError("exclusions section must be a list or mapping")


def _parse_exclusion_rule(item: Any) -> ExclusionRule:
    if isinstance(item, str):
        value = item.strip()
        if not value:
            raise ValueError("exclusion entries must not be empty strings")
        return ExclusionRule(kind="id", value=value)

    if isinstance(item, Mapping):
        reason = _sanitize_reason(item.get("reason"))
        if "id" in item and item["id"]:
            return ExclusionRule(kind="id", value=str(item["id"]), reason=reason)
        if "owner" in item and item["owner"]:
            return ExclusionRule(kind="owner", value=str(item["owner"]), reason=reason)
        if "owned_by" in item and item["owned_by"]:
            return ExclusionRule(kind="owner", value=str(item["owned_by"]), reason=reason)
        raise ValueError("exclusion mapping must include 'id' or 'owner'")

    raise ValueError("unsupported exclusion entry")


def _sanitize_reason(value: Any) -> Optional[str]:
    if value is None:
        return None
    reason = str(value).strip()
    return reason or None
