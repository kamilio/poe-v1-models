from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Union


def build_changelog_entry(
    current_payload: Mapping[str, Any],
    previous_payload: Optional[Mapping[str, Any]] = None,
    *,
    timestamp: Optional[Union[str, datetime]] = None,
) -> Dict[str, Any]:
    """Construct a changelog entry describing model additions/removals."""
    current_ids = _model_ids(current_payload.get("data", []))
    previous_ids: Set[str] = set()
    if previous_payload:
        previous_ids = _model_ids(previous_payload.get("data", []))

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
    snapshots: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    """Return changelog entries from ordered release snapshots."""
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
