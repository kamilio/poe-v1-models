from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence, TypedDict

from poe_v1_models.pricing import MTOK_MULTIPLIER, PricingSnapshot

@dataclass(frozen=True)
class ProviderReportColumn:
    """Definition describing how a provider attribute should appear in reports."""

    key: str
    label: str
    path: str
    numeric: bool = False


DEFAULT_REPORT_COLUMNS: Sequence[ProviderReportColumn] = (
    ProviderReportColumn(key="status", label="Status", path="status"),
    ProviderReportColumn(
        key="prompt_mtok",
        label="Prompt / MTok",
        path="pricing.prompt_mtok",
        numeric=True,
    ),
    ProviderReportColumn(
        key="completion_mtok",
        label="Completion / MTok",
        path="pricing.completion_mtok",
        numeric=True,
    ),
    ProviderReportColumn(
        key="input_cache_read_mtok",
        label="Input Cache Read / MTok",
        path="pricing.input_cache_read_mtok",
        numeric=True,
    ),
    ProviderReportColumn(
        key="input_cache_write_mtok",
        label="Input Cache Write / MTok",
        path="pricing.input_cache_write_mtok",
        numeric=True,
    ),
)


class ProviderPricingPayload(TypedDict, total=False):
    """Normalized pricing fields returned from provider transforms."""

    prompt: Optional[Decimal]
    completion: Optional[Decimal]
    request: Optional[Decimal]
    image: Optional[Decimal]
    input_cache_read: Optional[Decimal]
    input_cache_write: Optional[Decimal]


@dataclass
class ProviderResult:
    """Pricing result returned by a provider lookup."""

    provider: str
    pricing: Optional[PricingSnapshot]
    metadata: Mapping[str, object] | None = None


class PricingProvider(ABC):
    """Abstraction representing an MSRP provider."""

    name: str

    def __init__(
        self,
        name: str,
        *,
        display_name: Optional[str] = None,
        token_unit: str = "per_token",
        report_columns: Optional[Sequence[ProviderReportColumn]] = None,
    ) -> None:
        self.name = name
        self.display_name = display_name or name
        self._token_unit = token_unit
        self._report_columns: Sequence[ProviderReportColumn] = (
            tuple(report_columns) if report_columns else DEFAULT_REPORT_COLUMNS
        )

    @abstractmethod
    def load(self) -> None:
        """Fetch remote metadata once before performing lookups."""

    @abstractmethod
    def find(self, key: str, poe_model: Mapping[str, object]) -> Optional[PricingSnapshot]:
        """Return pricing information for the given provider-specific key."""

    @abstractmethod
    def transform(self, payload: Mapping[str, Any]) -> ProviderPricingPayload:
        """Normalise provider metadata into a standard pricing payload."""

    def default_key(self, poe_model: Mapping[str, object]) -> Optional[str]:
        """Infer a provider key based on Poe metadata, used when mapping contains 'auto'."""
        return None

    @property
    def report_columns(self) -> Sequence[ProviderReportColumn]:
        return self._report_columns

    def _normalise_token_price(self, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is None:
            return None
        if self._token_unit == "per_million":
            return value / MTOK_MULTIPLIER
        return value

    def build_snapshot(
        self,
        *,
        prompt: Optional[Decimal] = None,
        completion: Optional[Decimal] = None,
        request: Optional[Decimal] = None,
        image: Optional[Decimal] = None,
        input_cache_read: Optional[Decimal] = None,
        input_cache_write: Optional[Decimal] = None,
    ) -> PricingSnapshot:
        """Construct a pricing snapshot applying provider-specific scaling."""
        return PricingSnapshot(
            prompt=self._normalise_token_price(prompt),
            completion=self._normalise_token_price(completion),
            request=request,
            image=image,
            input_cache_read=self._normalise_token_price(input_cache_read),
            input_cache_write=self._normalise_token_price(input_cache_write),
        )

    def build_snapshot_from_payload(self, payload: ProviderPricingPayload) -> PricingSnapshot:
        """Construct a snapshot from a normalised provider payload."""
        return self.build_snapshot(
            prompt=payload.get("prompt"),
            completion=payload.get("completion"),
            request=payload.get("request"),
            image=payload.get("image"),
            input_cache_read=payload.get("input_cache_read"),
            input_cache_write=payload.get("input_cache_write"),
        )
