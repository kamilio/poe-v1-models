from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.changelog import build_changelog_entry


def parse_iso(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def test_changelog_initial_snapshot_marks_added():
    current_payload = {
        "object": "list",
        "data": [
            {"id": "model-a"},
            {"id": "model-b"},
        ],
    }

    entry = build_changelog_entry(current_payload, None)

    assert isinstance(entry["date"], str)
    # ensure timestamp parseable
    parse_iso(entry["date"])
    assert entry["initial_snapshot"] is True
    assert entry["total_models"] == 2
    assert entry["added"] == ["model-a", "model-b"]
    assert entry["removed"] == []


def test_changelog_computes_added_and_removed():
    current_payload = {
        "data": [
            {"id": "model-a"},
            {"id": "model-c"},
        ]
    }
    previous_payload = {
        "data": [
            {"id": "model-a"},
            {"id": "model-b"},
        ]
    }

    entry = build_changelog_entry(current_payload, previous_payload)

    assert isinstance(entry["date"], str)
    parse_iso(entry["date"])
    assert entry["total_models"] == 2
    assert entry["added"] == ["model-c"]
    assert entry["removed"] == ["model-b"]
