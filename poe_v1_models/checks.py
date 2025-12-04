from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from poe_v1_models.pricing import PricingSnapshot, PricingWithMtok, has_values


@dataclass
class ProviderDecision:
    provider: str
    status: str  # accepted, rejected, missing
    pricing: Optional[PricingSnapshot]
    reasons: List[str] = field(default_factory=list)

    def reject(self, reason: str) -> None:
        if reason not in self.reasons:
            self.reasons.append(reason)
        if self.status != "missing":
            self.status = "rejected"


@dataclass
class ModelChecks:
    poe_id: str
    decisions: Dict[str, ProviderDecision]
    selected_provider: Optional[str]
    poe_pricing: PricingWithMtok


def evaluate_provider_decisions(
    provider_priority: Sequence[str],
    provider_pricing: Mapping[str, Optional[PricingSnapshot]],
    poe_pricing: PricingWithMtok,
    *,
    disabled_providers: Optional[Iterable[str]] = None,
) -> Tuple[Dict[str, ProviderDecision], Optional[str]]:
    disabled: Set[str] = set(disabled_providers or [])
    all_providers = ordered_unique(
        list(provider_priority)
        + list(provider_pricing.keys())
        + list(disabled)
    )
    decisions: Dict[str, ProviderDecision] = {}

    for provider in all_providers:
        if provider in disabled:
            decisions[provider] = ProviderDecision(
                provider=provider,
                status="disabled",
                pricing=None,
                reasons=["mapping_disabled"],
            )
            continue
        snapshot = provider_pricing.get(provider)
        if not has_values(snapshot):
            decisions[provider] = ProviderDecision(provider=provider, status="missing", pricing=snapshot, reasons=["no_pricing_data"])
            continue

        reasons: List[str] = []
        if snapshot.prompt == Decimal("0"):
            reasons.append("zero_prompt_price")
        if snapshot.completion == Decimal("0"):
            reasons.append("zero_completion_price")

        if snapshot.prompt is not None and poe_pricing.prompt is not None and snapshot.prompt < poe_pricing.prompt:
            reasons.append("lower_than_poe_prompt")
        if snapshot.completion is not None and poe_pricing.completion is not None and snapshot.completion < poe_pricing.completion:
            reasons.append("lower_than_poe_completion")

        price_equal = False
        if snapshot.prompt is not None and poe_pricing.prompt is not None and snapshot.prompt == poe_pricing.prompt:
            price_equal = True
        if snapshot.completion is not None and poe_pricing.completion is not None and snapshot.completion == poe_pricing.completion:
            price_equal = True
        if price_equal:
            reasons.append("price_equal")

        status = "accepted" if not reasons else "rejected"
        decisions[provider] = ProviderDecision(provider=provider, status=status, pricing=snapshot, reasons=reasons)

    apply_conflict_checks(decisions)

    selected = pick_selected_provider(provider_priority, decisions)
    return decisions, selected


def apply_conflict_checks(decisions: Dict[str, ProviderDecision]) -> None:
    for field in ("prompt", "completion"):
        values: Dict[str, Decimal] = {}
        for provider, decision in decisions.items():
            snapshot = decision.pricing
            if decision.status in ("missing", "disabled") or snapshot is None:
                continue
            value = getattr(snapshot, field)
            if value is not None:
                values[provider] = value

        if len(set(values.values())) > 1:
            reason = f"conflict_{field}"
            for provider in values.keys():
                decisions[provider].reject(reason)


def pick_selected_provider(priority: Sequence[str], decisions: Mapping[str, ProviderDecision]) -> Optional[str]:
    for provider in priority:
        decision = decisions.get(provider)
        if decision and decision.status == "accepted":
            return provider
    # fallback to any accepted provider not in priority list
    for provider, decision in decisions.items():
        if decision.status == "accepted":
            return provider
    return None


def ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered
