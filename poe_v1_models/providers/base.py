from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping, Optional

from poe_v1_models.pricing import PricingSnapshot


@dataclass
class ProviderResult:
    """Pricing result returned by a provider lookup."""

    provider: str
    pricing: Optional[PricingSnapshot]
    metadata: Mapping[str, object] | None = None


class PricingProvider(ABC):
    """Abstraction representing an MSRP provider."""

    name: str

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def load(self) -> None:
        """Fetch remote metadata once before performing lookups."""

    @abstractmethod
    def find(self, key: str, poe_model: Mapping[str, object]) -> Optional[PricingSnapshot]:
        """Return pricing information for the given provider-specific key."""

    def default_key(self, poe_model: Mapping[str, object]) -> Optional[str]:
        """Infer a provider key based on Poe metadata, used when mapping contains 'auto'."""
        return None
