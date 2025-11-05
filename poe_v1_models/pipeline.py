from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.request import urlopen

from poe_v1_models.checks import ProviderDecision, evaluate_provider_decisions
from poe_v1_models.config import GeneralConfig, load_general_config
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


POE_API_URL = "https://api.poe.com/v1/models"


@dataclass
class ModelAggregate:
    poe_id: str
    normalized_pricing: PricingWithMtok
    provider_pricing: Dict[str, Optional[PricingSnapshot]]
    decisions: Dict[str, ProviderDecision]
    selected_provider: Optional[str]
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

        if config.exclusions.should_exclude(model):
            excluded[model_id] = model
            continue

        model = copy.deepcopy(model)
        normalized_pricing = normalize_pricing(model.get("pricing"))
        pricing_dict = normalized_pricing.as_dict()
        msrp_fields = {
            "msrp_prompt": None,
            "msrp_completion": None,
            "msrp_prompt_mtok": None,
            "msrp_completion_mtok": None,
        }

        provider_pricing: Dict[str, Optional[PricingSnapshot]] = {}
        decisions: Dict[str, ProviderDecision] = {}
        selected_provider: Optional[str] = None

        mapping_entry = mapping_by_id.get(model_id)
        if mapping_entry:
            provider_names = ordered_unique(
                list(config.providers.priority) + list(mapping_entry.providers())
            )
            for provider_name in provider_names:
                provider = providers.get(provider_name)
                if provider is None:
                    continue
                key = mapping_entry.key_for_provider(provider_name)
                if key is None:
                    continue
                pricing = provider.find(key, model)
                provider_pricing[provider_name] = pricing
            decisions, selected_provider = evaluate_provider_decisions(
                config.providers.priority,
                provider_pricing,
                normalized_pricing,
            )

            if selected_provider:
                chosen_pricing = provider_pricing.get(selected_provider)
                if chosen_pricing:
                    msrp_fields.update(as_msrp_fields(chosen_pricing))

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
            overrides_applied=overrides_applied,
        )

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


def fetch_json(url: str) -> Dict[str, Any]:
    with urlopen(url) as response:  # nosec: B310 - API is HTTPS and trusted
        if response.status != 200:
            raise RuntimeError(f"Failed to fetch {url}: {response.status}")
        return json.load(response)


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
