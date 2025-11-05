from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from poe_v1_models.checks import ProviderDecision
from poe_v1_models.pipeline import PipelineResult
from poe_v1_models.pricing import PricingSnapshot


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "src"


def _read_html_template(filename: str) -> str:
    """Load an HTML template from the src directory."""
    path = TEMPLATES_DIR / filename
    return path.read_text(encoding="utf-8")


def build_checks_report(result: PipelineResult) -> Dict[str, Any]:
    models: List[Dict[str, Any]] = []

    for model in result.payload.get("data", []):
        model_id = model.get("id")
        aggregate = result.aggregates.get(model_id)
        if not aggregate:
            continue

        model_entry: Dict[str, Any] = {
            "id": model_id,
            "selected_provider": aggregate.selected_provider,
            "overrides_applied": aggregate.overrides_applied,
            "poe_pricing": aggregate.normalized_pricing.as_dict(),
            "providers": [],
            "excluded": False,
        }

        for provider, decision in aggregate.decisions.items():
            model_entry["providers"].append(_provider_entry(provider, decision))

        models.append(model_entry)

    for model_id, model_data in result.excluded_models.items():
        models.append(
            {
                "id": model_id,
                "selected_provider": None,
                "overrides_applied": False,
                "poe_pricing": None,
                "providers": [],
                "excluded": True,
                "exclusion_reason": "config_exclusion",
                "owned_by": model_data.get("owned_by"),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": models,
    }


def _provider_entry(name: str, decision: ProviderDecision) -> Dict[str, Any]:
    pricing_payload: Optional[Dict[str, Any]] = None
    if decision.pricing:
        pricing_payload = _snapshot_dict(decision.pricing)

    severity = "ok"
    if decision.status == "missing":
        severity = "muted"
    elif decision.status == "rejected":
        if any(reason.startswith("lower_than_poe") for reason in decision.reasons):
            severity = "red"
        else:
            severity = "yellow"

    return {
        "name": name,
        "status": decision.status,
        "reasons": list(decision.reasons),
        "severity": severity,
        "pricing": pricing_payload,
    }


def _snapshot_dict(pricing: PricingSnapshot) -> Dict[str, Any]:
    enriched = pricing.with_mtok()
    payload = enriched.as_dict()
    payload["prompt"] = payload.get("prompt")
    payload["completion"] = payload.get("completion")
    return payload


def render_checks_html() -> str:
    return _read_html_template("checks.html")


def render_index_html() -> str:
    return _read_html_template("index.html")


def render_changelog_html() -> str:
    return _read_html_template("changelog.html")
