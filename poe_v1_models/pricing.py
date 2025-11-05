from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional


MTOK_MULTIPLIER = Decimal(1_000_000)


@dataclass
class PricingSnapshot:
    """Representation of per-token pricing values."""

    prompt: Optional[Decimal] = None
    completion: Optional[Decimal] = None
    image: Optional[Decimal] = None
    request: Optional[Decimal] = None

    def with_mtok(self) -> PricingWithMtok:
        """Return a richer view that includes per-million token values."""
        return PricingWithMtok(
            prompt=self.prompt,
            completion=self.completion,
            image=self.image,
            request=self.request,
            prompt_mtok=_mul_mtok(self.prompt),
            completion_mtok=_mul_mtok(self.completion),
        )


@dataclass
class PricingWithMtok(PricingSnapshot):
    """Snapshot that also includes per-million token values."""

    prompt_mtok: Optional[Decimal] = None
    completion_mtok: Optional[Decimal] = None

    def as_dict(self) -> Dict[str, Optional[str]]:
        """Serialise the snapshot into strings expected by the output schema."""
        payload: Dict[str, Optional[str]] = {
            "prompt": decimal_to_string(self.prompt) if self.prompt is not None else None,
            "completion": decimal_to_string(self.completion) if self.completion is not None else None,
            "image": decimal_to_string(self.image) if self.image is not None else None,
            "request": decimal_to_string(self.request) if self.request is not None else None,
            "prompt_mtok": decimal_to_string(self.prompt_mtok) if self.prompt_mtok is not None else None,
            "completion_mtok": decimal_to_string(self.completion_mtok) if self.completion_mtok is not None else None,
        }
        return payload


def decimal_or_none(value: Any) -> Optional[Decimal]:
    """Convert a raw value to Decimal, returning None if conversion fails."""
    if value in (None, "", 0):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def decimal_to_string(value: Decimal) -> str:
    """Format Decimal without scientific notation or trailing zeros."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def normalize_pricing(pricing: Optional[Dict[str, Any]]) -> PricingWithMtok:
    """Normalise Poe pricing payload into a PricingSnapshot."""
    source = pricing or {}
    snapshot = PricingSnapshot(
        prompt=decimal_or_none(source.get("prompt")),
        completion=decimal_or_none(source.get("completion")),
        image=decimal_or_none(source.get("image")),
        request=decimal_or_none(source.get("request")),
    )
    return snapshot.with_mtok()


def _mul_mtok(value: Optional[Decimal]) -> Optional[Decimal]:
    if value is None:
        return None
    return value * MTOK_MULTIPLIER


def as_msrp_fields(pricing: PricingSnapshot) -> Dict[str, Optional[str]]:
    """Render MSRP pricing into the schema expected by Poe output."""
    enriched = pricing.with_mtok()
    return {
        "msrp_prompt": decimal_to_string(enriched.prompt) if enriched.prompt is not None else None,
        "msrp_completion": decimal_to_string(enriched.completion) if enriched.completion is not None else None,
        "msrp_prompt_mtok": decimal_to_string(enriched.prompt_mtok) if enriched.prompt_mtok is not None else None,
        "msrp_completion_mtok": decimal_to_string(enriched.completion_mtok) if enriched.completion_mtok is not None else None,
    }
