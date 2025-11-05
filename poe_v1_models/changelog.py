from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional, Set


def build_changelog_entry(
    current_payload: Mapping[str, Any],
    previous_payload: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Construct a changelog entry describing model additions/removals."""
    current_ids = _model_ids(current_payload.get("data", []))
    previous_ids: Set[str] = set()
    if previous_payload:
        previous_ids = _model_ids(previous_payload.get("data", []))

    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)

    entry: Dict[str, Any] = {
        "date": datetime.now(timezone.utc).isoformat(),
        "total_models": len(current_ids),
        "added": added,
        "removed": removed,
    }
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
