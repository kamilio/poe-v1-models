from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
import xml.etree.ElementTree as ET

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
            lookup_metadata = aggregate.provider_lookup.get(provider_name)
            providers_payload[provider_name] = _serialize_provider_decision(
                decision,
                columns,
                selected=aggregate.selected_provider == provider_name,
                lookup=lookup_metadata,
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
    lookup: Optional[Mapping[str, Optional[str]]] = None,
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

    lookup_payload: Dict[str, Optional[str]] = {"requested": None, "resolved": None}
    if lookup:
        lookup_payload["requested"] = lookup.get("requested")
        lookup_payload["resolved"] = lookup.get("resolved")

    return {
        "status": decision.status,
        "severity": _decision_severity(decision),
        "selected": selected,
        "values": values,
        "lookup": lookup_payload,
        "reasons": list(decision.reasons),
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


def render_changelog_rss(
    entries: Sequence[Mapping[str, Any]],
    *,
    base_url: Optional[str] = None,
) -> str:
    """Render changelog entries into an RSS feed.

    NOTE: Keep this content aligned with the interactive changelog page (src/changelog.html).
    Updates to one should generally be mirrored in the other so both surfaces stay in sync.
    """
    normalised_base = _normalise_base_url(base_url)
    channel_link = normalised_base + "changelog.html"
    now = datetime.now(timezone.utc)

    rss = ET.Element("rss", attrib={"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Poe V1 Models Changelog"
    ET.SubElement(channel, "link").text = channel_link
    ET.SubElement(channel, "description").text = "Updates to the Poe V1 model catalogue and MSRP metadata."
    ET.SubElement(channel, "language").text = "en"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(now)

    sorted_entries = sorted(
        entries,
        key=lambda item: item.get("date") or "",
        reverse=True,
    )

    for entry in sorted_entries:
        timestamp = _parse_entry_timestamp(entry.get("date"))
        display_date = timestamp.strftime("%Y-%m-%d %H:%M UTC")
        title_suffix = _summarise_entry(entry)
        title_text = f"{display_date} — {title_suffix}" if title_suffix else display_date

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title_text
        ET.SubElement(item, "link").text = _entry_link(entry, channel_link)
        guid_value, guid_is_permalink = _entry_guid(entry, display_date)
        guid_attributes: Dict[str, str] = {"isPermaLink": "true" if guid_is_permalink else "false"}
        ET.SubElement(item, "guid", attrib=guid_attributes).text = guid_value
        ET.SubElement(item, "pubDate").text = format_datetime(timestamp)
        ET.SubElement(item, "description").text = _entry_description(entry)

    xml_bytes = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


def _normalise_base_url(base_url: Optional[str]) -> str:
    fallback = "https://github.com/poe-v1-models/poe-v1-models/"
    if base_url:
        candidate = base_url.strip()
        if candidate:
            if not candidate.endswith("/"):
                candidate += "/"
            return candidate
    return fallback


def _parse_entry_timestamp(value: Any) -> datetime:
    if isinstance(value, str) and value:
        cleaned = value.strip()
        if cleaned:
            try:
                return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            except ValueError:
                pass
    return datetime.now(timezone.utc)


def _summarise_entry(entry: Mapping[str, Any]) -> str:
    parts: List[str] = []
    added = entry.get("added")
    removed = entry.get("removed")
    price_changes = entry.get("price_changes")

    if isinstance(added, list) and added:
        parts.append(f"+{len(added)} added")
    if isinstance(removed, list) and removed:
        parts.append(f"-{len(removed)} removed")
    if isinstance(price_changes, list) and price_changes:
        parts.append(f"{len(price_changes)} price adjustments")

    if not parts:
        total_models = entry.get("total_models")
        if isinstance(total_models, int):
            return f"{total_models} models total"
        return "No changes recorded"
    return ", ".join(parts)


def _entry_link(entry: Mapping[str, Any], fallback: str) -> str:
    release_url = entry.get("release_url")
    if isinstance(release_url, str) and release_url:
        return release_url
    return fallback


def _entry_guid(entry: Mapping[str, Any], fallback_date: str) -> tuple[str, bool]:
    release_url = entry.get("release_url")
    if isinstance(release_url, str) and release_url:
        return release_url, True
    reference = entry.get("date")
    total = entry.get("total_models")
    guid = f"{reference}|{total}" if reference else fallback_date
    return guid, False


def _entry_description(entry: Mapping[str, Any]) -> str:
    lines: List[str] = []
    total_models = entry.get("total_models")
    if isinstance(total_models, int):
        lines.append(f"Total models: {total_models}")

    for label, values in (
        ("Added", entry.get("added")),
        ("Removed", entry.get("removed")),
    ):
        if isinstance(values, list) and values:
            lines.append(f"{label}: {', '.join(values)}")

    price_changes = entry.get("price_changes")
    if isinstance(price_changes, list) and price_changes:
        lines.append("Price changes:")
        for change in price_changes:
            model_id = change.get("id")
            if isinstance(model_id, str) and model_id:
                lines.append(f"  - {model_id}")
            fields = change.get("fields")
            if isinstance(fields, list):
                for field in fields:
                    name = field.get("field")
                    previous = _value_with_dash(field.get("previous"))
                    current = _value_with_dash(field.get("current"))
                    delta = field.get("delta")
                    direction = field.get("direction")
                    summary = f"{previous} → {current}"
                    if isinstance(delta, str) and delta:
                        summary = f"{summary} ({delta})"
                    if isinstance(direction, str) and direction:
                        summary = f"{summary} [{direction}]"
                    lines.append(f"    · {name}: {summary}")

    if not lines:
        lines.append("No changes recorded.")
    return "\n".join(lines)


def _value_with_dash(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    return "—"
