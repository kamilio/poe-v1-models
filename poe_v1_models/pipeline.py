from __future__ import annotations

import copy
import json
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from poe_v1_models.checks import ProviderDecision, evaluate_provider_decisions
from poe_v1_models.config import BoostSettings, GeneralConfig, load_general_config
from poe_v1_models.mapping import ModelMappingEntry, load_model_mapping, mapping_index
from poe_v1_models.pricing import (
    PricingSnapshot,
    PricingWithMtok,
    as_msrp_fields,
    normalize_pricing,
)
from poe_v1_models.providers.base import PricingProvider
from poe_v1_models.providers.models_dev import ModelsDevProvider
from poe_v1_models.providers.openrouter import OpenRouterProvider
from poe_v1_models.providers.utils import AUTO_MAPPING_KEY, is_none_mapping


POE_API_URL = "https://api.poe.com/v1/models"
_HUMANISH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "DNT": "1",
}


@dataclass
class ModelAggregate:
    poe_id: str
    normalized_pricing: PricingWithMtok
    provider_pricing: Dict[str, Optional[PricingSnapshot]]
    decisions: Dict[str, ProviderDecision]
    selected_provider: Optional[str]
    provider_lookup: Dict[str, Dict[str, Optional[str]]]
    overrides_applied: bool = False


@dataclass
class PipelineResult:
    payload: Dict[str, Any]
    aggregates: Dict[str, ModelAggregate]
    excluded_models: Dict[str, Mapping[str, Any]]
    config: GeneralConfig
    providers: Dict[str, PricingProvider]


def run_pipeline() -> PipelineResult:
    """Execute the pricing enrichment pipeline."""
    config = load_general_config()
    mapping_entries = load_model_mapping()
    poe_payload = load_poe_models()

    providers = prepare_providers(config.providers.priority, mapping_entries)
    mapping_by_id = mapping_index(mapping_entries)

    enriched_models: List[Dict[str, Any]] = []
    aggregates: Dict[str, ModelAggregate] = {}
    excluded: Dict[str, Mapping[str, Any]] = {}

    for model in poe_payload.get("data", []):
        model_id = model.get("id")
        if not isinstance(model_id, str):
            continue

        exclusion_rule = config.exclusions.rule_for(model)
        if exclusion_rule:
            excluded_payload = copy.deepcopy(model)
            excluded_payload["_config_exclusion_rule"] = exclusion_rule.kind
            if exclusion_rule.reason:
                excluded_payload["_config_exclusion_reason"] = exclusion_rule.reason
            excluded[model_id] = excluded_payload
            continue

        model = copy.deepcopy(model)
        normalized_pricing = normalize_pricing(model.get("pricing"))
        pricing_dict = normalized_pricing.as_dict()
        msrp_fields = {
            "msrp_prompt": None,
            "msrp_completion": None,
            "msrp_prompt_mtok": None,
            "msrp_completion_mtok": None,
            "msrp_input_cache_read": None,
            "msrp_input_cache_write": None,
            "msrp_input_cache_read_mtok": None,
            "msrp_input_cache_write_mtok": None,
        }

        provider_pricing: Dict[str, Optional[PricingSnapshot]] = {}
        provider_lookup: Dict[str, Dict[str, Optional[str]]] = {}
        decisions: Dict[str, ProviderDecision] = {}
        selected_provider: Optional[str] = None
        disabled_providers: set[str] = set()

        mapping_entry = mapping_by_id.get(model_id)
        provider_names = ordered_unique(
            list(config.providers.priority)
            + (list(mapping_entry.providers()) if mapping_entry else [])
        )

        for provider_name in provider_names:
            provider = providers.get(provider_name)
            if provider is None:
                continue
            key = mapping_entry.key_for_provider(provider_name) if mapping_entry else None
            if key is None or key.strip() == "":
                key = AUTO_MAPPING_KEY
            requested_key = key.strip()
            if requested_key == "":
                requested_key = AUTO_MAPPING_KEY
            if is_none_mapping(requested_key):
                provider_lookup[provider_name] = {
                    "requested": "none",
                    "resolved": None,
                }
                disabled_providers.add(provider_name)
                continue
            lookup_info = _summarise_provider_lookup(provider, requested_key, model)
            provider_lookup[provider_name] = lookup_info
            lookup_key = lookup_info.get("requested")
            if lookup_key is None:
                lookup_key = requested_key
            pricing = provider.find(lookup_key, model)
            provider_pricing[provider_name] = pricing

        if provider_pricing or disabled_providers:
            decisions, selected_provider = evaluate_provider_decisions(
                config.providers.priority,
                provider_pricing,
                normalized_pricing,
                disabled_providers=disabled_providers,
            )

            if selected_provider:
                chosen_pricing = provider_pricing.get(selected_provider)
                if chosen_pricing:
                    msrp_fields.update(_msrp_fields_with_discount(chosen_pricing, normalized_pricing))

        pricing_dict.update(msrp_fields)
        model["pricing"] = pricing_dict

        # Apply overrides if present.
        override = config.overrides.get(model_id)
        overrides_applied = False
        if override:
            deep_merge(model, override)
            overrides_applied = True

        enriched_models.append(model)
        aggregates[model_id] = ModelAggregate(
            poe_id=model_id,
            normalized_pricing=normalized_pricing,
            provider_pricing=provider_pricing,
            decisions=decisions,
            selected_provider=selected_provider,
            provider_lookup=provider_lookup,
            overrides_applied=overrides_applied,
        )

    enriched_models = _apply_boosts(enriched_models, config.boosts)

    payload = {
        "object": poe_payload.get("object"),
        "data": enriched_models,
    }
    return PipelineResult(
        payload=payload,
        aggregates=aggregates,
        excluded_models=excluded,
        config=config,
        providers=providers,
    )


def prepare_providers(priority: Sequence[str], mapping_entries: Iterable[ModelMappingEntry]) -> Dict[str, PricingProvider]:
    """Instantiate and load providers required by configuration and mapping."""
    provider_names = set(priority)
    for entry in mapping_entries:
        provider_names.update(entry.providers())

    providers: Dict[str, PricingProvider] = {}
    for name in provider_names:
        provider = build_provider(name)
        if provider:
            provider.load()
            providers[name] = provider
    return providers


def build_provider(name: str) -> Optional[PricingProvider]:
    if name == "models.dev":
        return ModelsDevProvider()
    if name == "openrouter":
        return OpenRouterProvider()
    return None


def load_poe_models(url: str = POE_API_URL) -> Dict[str, Any]:
    return fetch_json(url)


def fetch_json(url: str, max_attempts: int = 3, base_backoff: float = 0.75) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        request = Request(url, headers=_HUMANISH_HEADERS)
        try:
            with urlopen(request, timeout=15) as response:  # nosec: B310 - API is HTTPS and trusted
                if response.status != 200:
                    raise RuntimeError(f"Failed to fetch {url}: {response.status}")
                return json.load(response)
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {403, 408, 425, 429, 500, 502, 503, 504} or attempt == max_attempts:
                raise
        except URLError as exc:
            last_error = exc
            if attempt == max_attempts:
                raise RuntimeError(f"Failed to fetch {url}") from exc

        _sleep_with_jitter(base_backoff, attempt)

    raise RuntimeError(f"Failed to fetch {url}") from last_error


def _sleep_with_jitter(base_backoff: float, attempt: int) -> None:
    delay = base_backoff * (2 ** (attempt - 1))
    jitter = random.uniform(0, base_backoff)
    time.sleep(delay + jitter)


def ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def deep_merge(target: Dict[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    """Deep merge override mapping into target."""
    for key, value in override.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, Mapping)
        ):
            deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def _summarise_provider_lookup(
    provider: PricingProvider,
    key: str,
    poe_model: Mapping[str, Any],
) -> Dict[str, Optional[str]]:
    """Capture mapping metadata for reporting."""
    requested = key.strip() if key is not None else None
    if requested == "":
        requested = None
    resolved = requested

    if requested is None or requested == "auto":
        resolved = provider.default_key(poe_model)
    elif requested == "none":
        resolved = None

    return {
        "requested": requested,
        "resolved": resolved,
    }


def _msrp_fields_with_discount(
    provider_pricing: PricingSnapshot,
    poe_pricing: PricingWithMtok,
) -> Dict[str, Optional[str]]:
    """Return MSRP fields only when provider pricing exceeds Poe pricing."""
    msrp_payload = as_msrp_fields(provider_pricing)
    has_discount = False

    comparisons = (
        ("prompt", "msrp_prompt"),
        ("completion", "msrp_completion"),
        ("input_cache_read", "msrp_input_cache_read"),
        ("input_cache_write", "msrp_input_cache_write"),
    )

    for attr, base_key in comparisons:
        provider_value = getattr(provider_pricing, attr, None)
        mtok_key = f"{base_key}_mtok"

        if provider_value is None:
            msrp_payload[base_key] = None
            if mtok_key in msrp_payload:
                msrp_payload[mtok_key] = None
            continue

        poe_value = getattr(poe_pricing, attr, None)
        if poe_value is None:
            has_discount = True
            continue

        if poe_value >= provider_value:
            msrp_payload[base_key] = None
            if mtok_key in msrp_payload:
                msrp_payload[mtok_key] = None
        else:
            has_discount = True

    if not has_discount:
        for key in msrp_payload.keys():
            msrp_payload[key] = None

    return msrp_payload


def _apply_boosts(models: List[Dict[str, Any]], boosts: BoostSettings) -> List[Dict[str, Any]]:
    if not boosts or not getattr(boosts, "rules", None):
        return models

    indexed_models = list(enumerate(models))
    total_rules = len(boosts.rules)

    def sort_key(item: tuple[int, Dict[str, Any]]) -> tuple[int, int]:
        index, model = item
        position = boosts.position_for(model)
        if position is None:
            return (total_rules, index)
        return (position, index)

    indexed_models.sort(key=sort_key)
    return [model for _, model in indexed_models]
