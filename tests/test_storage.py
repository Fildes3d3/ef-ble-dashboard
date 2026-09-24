"""The schema is generated from the dataclasses, so these test the generator."""

import sqlite3
from datetime import UTC, datetime, timedelta

from app.devices import ALTERNATOR, DELTA2
from app.models import Snapshot
from app.storage import TelemetryStore


def recent(minutes_ago: int = 0) -> str:
    """A timestamp inside the 30-day retention window.

    Rows older than that are deleted on every insert, so fixed past dates vanish
    and make assertions pass against an empty table.
    """
    return (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()


def columns(store):
    return {row[1] for row in store.connection.execute(
        f"PRAGMA table_info({store.kind.table})")}


def test_schema_matches_the_dataclass(store):
    assert columns(store) == set(DELTA2.fields)


def test_each_device_gets_its_own_table(tmp_path):
    db = tmp_path / "shared.sqlite3"
    a = TelemetryStore(db, DELTA2)
    b = TelemetryStore(db, ALTERNATOR)
    try:
        assert a.kind.table != b.kind.table
        assert columns(a) != columns(b)
    finally:
        a.close()
        b.close()


def test_migration_adds_columns_without_losing_rows(tmp_path):
    """The real upgrade path: an old table gains columns, keeps its data."""
    db = tmp_path / "old.sqlite3"
    legacy = sqlite3.connect(db)
    legacy.execute(
        "CREATE TABLE snapshots (timestamp TEXT PRIMARY KEY, battery_level REAL)")
    stamp = recent()
    legacy.execute("INSERT INTO snapshots VALUES (?, 42.0)", (stamp,))
    legacy.commit()
    legacy.close()

    store = TelemetryStore(db, DELTA2)
    try:
        assert columns(store) == set(DELTA2.fields)
        kept = store.connection.execute(
            "SELECT timestamp, battery_level FROM snapshots").fetchall()
        assert kept == [(stamp, 42.0)]
    finally:
        store.close()


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / "twice.sqlite3"
    first = TelemetryStore(db, DELTA2)
    first.add(Snapshot(timestamp=recent(), battery_level=50.0))
    first.close()
    second = TelemetryStore(db, DELTA2)
    try:
        assert second.history()[0]["battery_level"] == 50.0
    finally:
        second.close()


def test_history_is_oldest_first(store):
    for minutes in (30, 90, 60):
        store.add(Snapshot(timestamp=recent(minutes)))
    stamps = [row["timestamp"] for row in store.history()]
    assert len(stamps) == 3, "retention deleted rows the test needs"
    assert stamps == sorted(stamps)


def test_missing_values_persist_as_null_not_zero(store):
    """A field the device did not report must not read back as 0."""
    store.add(Snapshot(timestamp=recent(), battery_level=50.0))
    row = store.history()[0]
    assert row["battery_level"] == 50.0
    assert row["ac_output_power"] is None


def test_retention_drops_rows_older_than_thirty_days(store):
    store.add(Snapshot(timestamp=recent(), battery_level=1.0))
    ancient = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    store.add(Snapshot(timestamp=ancient, battery_level=2.0))
    kept = [row["timestamp"] for row in store.history()]
    assert ancient not in kept
    assert len(kept) == 1
