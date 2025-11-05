from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from poe_v1_models.checks import ProviderDecision
from poe_v1_models.providers.base import ProviderReportColumn, PricingProvider
from poe_v1_models.pipeline import PipelineResult


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "src"


def _read_html_template(filename: str) -> str:
    """Load an HTML template from the src directory."""
    path = TEMPLATES_DIR / filename
    return path.read_text(encoding="utf-8")


def build_checks_report(result: PipelineResult) -> Dict[str, Any]:
    provider_order = _provider_order(result.providers, result.aggregates.values(), result.config.providers.priority)
    provider_columns: Dict[str, Sequence[ProviderReportColumn]] = {}
    providers_meta: List[Dict[str, Any]] = []

    for name in provider_order:
        provider = result.providers.get(name)
        if not provider:
            continue
        columns = tuple(provider.report_columns)
        provider_columns[name] = columns
        providers_meta.append(
            {
                "name": name,
                "label": getattr(provider, "display_name", name),
                "columns": [
                    {
                        "key": column.key,
                        "label": column.label,
                        "numeric": column.numeric,
                    }
                    for column in columns
                ],
            }
        )

    models: List[Dict[str, Any]] = []
    for model in result.payload.get("data", []):
        model_id = model.get("id")
        aggregate = result.aggregates.get(model_id)
        if aggregate is None:
            continue
        providers_payload: Dict[str, Any] = {}
        for provider_name, columns in provider_columns.items():
            decision = aggregate.decisions.get(provider_name)
            if decision is None:
                continue
            providers_payload[provider_name] = _serialize_provider_decision(
                decision,
                columns,
                selected=aggregate.selected_provider == provider_name,
            )

        models.append(
            {
                "id": model_id,
                "owned_by": model.get("owned_by"),
                "selected_provider": aggregate.selected_provider,
                "overrides_applied": aggregate.overrides_applied,
                "poe_pricing": aggregate.normalized_pricing.as_dict(),
                "providers": providers_payload,
            }
        )

    excluded: List[Dict[str, Any]] = []
    for model_id, model_data in result.excluded_models.items():
        reason = model_data.get("_config_exclusion_reason") if isinstance(model_data, Mapping) else None
        rule_type = model_data.get("_config_exclusion_rule") if isinstance(model_data, Mapping) else None

        payload: Dict[str, Any] = {
            "id": model_id,
            "owned_by": model_data.get("owned_by") if isinstance(model_data, Mapping) else None,
            "reason": reason or "config_exclusion",
        }
        if rule_type:
            payload["rule_type"] = rule_type
        excluded.append(payload)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "providers": providers_meta,
        "models": models,
        "excluded_models": excluded,
    }


def _provider_order(
    providers: Mapping[str, PricingProvider],
    aggregates: Iterable[Any],
    priority: Sequence[str],
) -> List[str]:
    ordered: List[str] = []
    seen = set()

    def add(name: Optional[str]) -> None:
        if not name or name in seen or name not in providers:
            return
        ordered.append(name)
        seen.add(name)

    for provider_name in priority:
        add(provider_name)

    for aggregate in aggregates:
        decisions = getattr(aggregate, "decisions", {}) or {}
        for provider_name in decisions.keys():
            add(provider_name)

    for provider_name in providers.keys():
        add(provider_name)
    return ordered


def _serialize_provider_decision(
    decision: ProviderDecision,
    columns: Sequence[ProviderReportColumn],
    *,
    selected: bool,
) -> Dict[str, Any]:
    pricing_payload: Dict[str, Any] = {}
    if decision.pricing:
        pricing_payload = decision.pricing.with_mtok().as_dict()

    payload: Dict[str, Any] = {
        "status": decision.status,
        "reasons": list(decision.reasons),
        "pricing": pricing_payload,
    }

    values: Dict[str, Dict[str, Any]] = {}
    for column in columns:
        raw_value = _extract_path(payload, column.path)
        values[column.key] = _render_column_value(column, raw_value)

    return {
        "status": decision.status,
        "severity": _decision_severity(decision),
        "selected": selected,
        "values": values,
    }


def _extract_path(payload: Mapping[str, Any], path: str) -> Any:
    current: Any = payload
    for segment in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(segment)
        else:
            return None
    return current


def _render_column_value(column: ProviderReportColumn, raw_value: Any) -> Dict[str, Any]:
    display = "—"
    html: Optional[str] = None

    if column.key == "status":
        status_text = str(raw_value or "missing")
        display = status_text
        html = f'<span class="tag {status_text}">{status_text}</span>'
    elif column.key == "reasons":
        if isinstance(raw_value, (list, tuple)):
            display = ", ".join(str(reason) for reason in raw_value) if raw_value else "—"
        elif raw_value not in (None, "", "null"):
            display = str(raw_value)
    else:
        if isinstance(raw_value, (list, tuple)):
            display = ", ".join(str(item) for item in raw_value) if raw_value else "—"
        elif raw_value not in (None, "", "null"):
            display = str(raw_value)

    payload: Dict[str, Any] = {"text": display}
    if html:
        payload["html"] = html
    if column.numeric:
        payload["numeric"] = True
    return payload


def _decision_severity(decision: ProviderDecision) -> str:
    severity = "ok"
    if decision.status == "missing":
        severity = "muted"
    elif decision.status == "rejected":
        if any(reason.startswith("lower_than_poe") for reason in decision.reasons):
            severity = "red"
        else:
            severity = "yellow"
    return severity


def render_checks_html() -> str:
    return _read_html_template("checks.html")


def render_index_html() -> str:
    return _read_html_template("index.html")


def render_changelog_html() -> str:
    return _read_html_template("changelog.html")
