from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.changelog import (
    build_changelog_entry,
    build_changelog_from_snapshots,
)


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


def test_changelog_entry_accepts_custom_timestamp():
    current_payload = {"data": [{"id": "model-a"}]}
    custom = "2024-05-04T12:00:00Z"

    entry = build_changelog_entry(current_payload, timestamp=custom)

    assert entry["date"] == custom
    assert entry["total_models"] == 1
    assert entry["added"] == ["model-a"]
    assert entry["removed"] == []
    assert entry["initial_snapshot"] is True


def test_build_changelog_from_snapshots_diffs_in_order():
    snapshots = [
        {
            "payload": {"data": [{"id": "model-a"}]},
            "timestamp": "2024-05-04T12:00:00Z",
            "metadata": {"tag": "v1"},
        },
        {
            "payload": {"data": [{"id": "model-a"}, {"id": "model-b"}]},
            "timestamp": "2024-05-05T12:00:00Z",
            "metadata": {"tag": "v2"},
        },
        {
            "payload": {"data": [{"id": "model-b"}]},
            "timestamp": "2024-05-06T12:00:00Z",
            "metadata": {"tag": "v3"},
        },
    ]

    entries = build_changelog_from_snapshots(snapshots)

    assert [entry["tag"] for entry in entries] == ["v1", "v2", "v3"]
    assert entries[0]["added"] == ["model-a"]
    assert entries[0]["removed"] == []
    assert entries[0]["initial_snapshot"] is True
    assert entries[1]["added"] == ["model-b"]
    assert entries[1]["removed"] == []
    assert entries[2]["added"] == []
    assert entries[2]["removed"] == ["model-a"]
