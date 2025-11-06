from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Union

from poe_v1_models.config import ExclusionSettings, GeneralConfig, load_general_config
from poe_v1_models.pricing import decimal_or_none, decimal_to_string


PRICING_FIELDS = (
    "prompt",
    "completion",
    "request",
    "image",
    "input_cache_read",
    "input_cache_write",
)


def build_changelog_entry(
    current_payload: Mapping[str, Any],
    previous_payload: Optional[Mapping[str, Any]] = None,
    *,
    timestamp: Optional[Union[str, datetime]] = None,
    exclusions: Optional[ExclusionSettings] = None,
) -> Dict[str, Any]:
    """Construct a changelog entry describing model additions/removals."""
    current_models = _payload_models(current_payload, exclusions)
    current_ids = _model_ids(current_models)
    previous_ids: Set[str] = set()
    previous_models: Sequence[Mapping[str, Any]] = []
    if previous_payload:
        previous_models = _payload_models(previous_payload, exclusions)
        previous_ids = _model_ids(previous_models)

    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)

    entry: Dict[str, Any] = {
        "date": _resolve_timestamp(timestamp),
        "total_models": len(current_ids),
    }
    if added:
        entry["added"] = added
    if removed:
        entry["removed"] = removed
    if previous_payload:
        price_changes = _build_price_changes(current_models, previous_models)
        if price_changes:
            entry["price_changes"] = price_changes
    if previous_payload is None:
        entry["initial_snapshot"] = True
    return entry


def _model_ids(models: Iterable[Any]) -> Set[str]:
    ids: Set[str] = set()
    for model in models:
        if not isinstance(model, Mapping):
            continue
        model_id = model.get("id")
        if isinstance(model_id, str):
            ids.add(model_id)
    return ids


def _resolve_timestamp(value: Optional[Union[str, datetime]]) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, datetime):
        resolved = value
        if value.tzinfo is None:
            resolved = value.replace(tzinfo=timezone.utc)
        return resolved.astimezone(timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def build_changelog_from_snapshots(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    config: Optional[GeneralConfig] = None,
) -> List[Dict[str, Any]]:
    """Return changelog entries from ordered release snapshots."""
    resolved_config = config or load_general_config()
    exclusions = resolved_config.exclusions if resolved_config else None
    entries: List[Dict[str, Any]] = []
    previous_payload: Optional[Mapping[str, Any]] = None

    for snapshot in snapshots:
        payload = snapshot.get("payload")
        if not isinstance(payload, Mapping):
            continue

        entry = build_changelog_entry(
            payload,
            previous_payload,
            timestamp=snapshot.get("timestamp"),
            exclusions=exclusions,
        )

        metadata = snapshot.get("metadata")
        if isinstance(metadata, Mapping):
            for key, value in metadata.items():
                if value is not None and key not in entry:
                    entry[key] = value

        should_include = (
            previous_payload is None
            or entry.get("added")
            or entry.get("removed")
        )
        if should_include:
            entries.append(entry)

        previous_payload = payload

    return entries


def _payload_models(
    payload: Optional[Mapping[str, Any]],
    exclusions: Optional[ExclusionSettings],
) -> List[Mapping[str, Any]]:
    models: List[Mapping[str, Any]] = []
    if not isinstance(payload, Mapping):
        return models
    for model in payload.get("data", []):
        if not isinstance(model, Mapping):
            continue
        if exclusions and exclusions.should_exclude(model):
            continue
        models.append(model)
    return models


def _build_price_changes(
    current_models: Iterable[Mapping[str, Any]],
    previous_models: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    current_index = _models_by_id(current_models)
    previous_index = _models_by_id(previous_models)

    shared_ids = sorted(set(current_index.keys()) & set(previous_index.keys()))
    price_changes: List[Dict[str, Any]] = []

    for model_id in shared_ids:
        current_model = current_index[model_id]
        previous_model = previous_index[model_id]
        field_changes = _diff_pricing_fields(current_model, previous_model)
        if field_changes:
            price_changes.append(
                {
                    "id": model_id,
                    "fields": field_changes,
                }
            )

    return price_changes


def _models_by_id(models: Iterable[Any]) -> Dict[str, Mapping[str, Any]]:
    index: Dict[str, Mapping[str, Any]] = {}
    for model in models:
        if not isinstance(model, Mapping):
            continue
        model_id = model.get("id")
        if isinstance(model_id, str):
            index[model_id] = model
    return index


def _diff_pricing_fields(
    current_model: Mapping[str, Any],
    previous_model: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    current_pricing = _as_mapping(current_model.get("pricing"))
    previous_pricing = _as_mapping(previous_model.get("pricing"))

    if current_pricing is None and previous_pricing is None:
        return []

    changes: List[Dict[str, Any]] = []
    for field in PRICING_FIELDS:
        current_value = decimal_or_none(current_pricing.get(field)) if current_pricing else None
        previous_value = decimal_or_none(previous_pricing.get(field)) if previous_pricing else None

        if current_value == previous_value:
            continue

        # Ignore transitions from no price to a populated value; they are represented as additions.
        if previous_value is None and current_value is not None:
            continue

        change: Dict[str, Any] = {
            "field": field,
            "previous": _decimal_or_null(previous_value),
            "current": _decimal_or_null(current_value),
        }

        direction = _direction(previous_value, current_value)
        if direction:
            change["direction"] = direction

        if previous_value is not None and current_value is not None:
            delta = current_value - previous_value
            if delta != 0:
                change["delta"] = decimal_to_string(delta)

        changes.append(change)

    return sorted(changes, key=lambda item: item["field"])


def _as_mapping(value: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return value
    return None


def _decimal_or_null(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return decimal_to_string(value)


def _direction(previous: Optional[Decimal], current: Optional[Decimal]) -> Optional[str]:
    if previous is None and current is None:
        return None
    if previous is None and current is not None:
        return "increase"
    if previous is not None and current is None:
        return "decrease"
    if previous is None or current is None:  # handled above, but keep defensive
        return None
    if current > previous:
        return "increase"
    if current < previous:
        return "decrease"
    return "unchanged"
