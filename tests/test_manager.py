"""The scheduler, and what it does when the machine wakes up."""

import asyncio
from dataclasses import replace

from app.collector import DeviceCollector
from app.devices import ALTERNATOR, DELTA2
from app.manager import CollectorManager
from app.storage import TelemetryStore


def build(settings, tmp_path):
    lock = asyncio.Lock()
    collectors = {
        kind.key: DeviceCollector(
            kind, settings, TelemetryStore(tmp_path / f"{kind.key}.sqlite3", kind), lock
        )
        for kind in (DELTA2, ALTERNATOR)
    }
    return CollectorManager(settings, collectors), collectors


async def test_wait_reports_a_small_overshoot_while_awake(settings, tmp_path):
    """A poll that runs normally overshoots by milliseconds, not minutes."""
    manager, collectors = build(replace(settings, poll_seconds=0), tmp_path)
    try:
        overshoot = await manager._wait()
        assert overshoot < manager.SUSPEND_THRESHOLD
    finally:
        for collector in collectors.values():
            collector.store.close()


async def test_wait_reports_the_overshoot_when_the_process_was_frozen(
    settings, tmp_path, monkeypatch
):
    """The real signal: a 15s sleep that took 470s of wall time.

    The previous approach compared the monotonic and wall clocks; on macOS both keep
    running across sleep, so a genuine 470-second suspend was missed entirely.
    """
    manager, collectors = build(replace(settings, poll_seconds=15), tmp_path)
    try:
        clock = iter([1000.0, 1470.0])          # before, after
        monkeypatch.setattr("app.manager.time.time", lambda: next(clock))

        async def instant(_seconds):
            return None

        monkeypatch.setattr("app.manager.asyncio.sleep", instant)
        overshoot = await manager._wait()
        assert overshoot == 455.0
        assert overshoot > manager.SUSPEND_THRESHOLD
    finally:
        for collector in collectors.values():
            collector.store.close()


async def test_wake_resets_every_collector(settings, tmp_path, monkeypatch):
    """The clocks diverging means the machine was away, so every handle is suspect."""
    manager, collectors = build(settings, tmp_path)
    try:
        for collector in collectors.values():
            collector._cached_device = ("stale", "handle")

        async def suspended_wait():
            manager._stop.set()          # one pass only
            return manager.SUSPEND_THRESHOLD + 1

        monkeypatch.setattr(manager, "_wait", suspended_wait)
        # Nothing is due, so no device is actually contacted.
        for collector in collectors.values():
            collector._next_attempt = 1e9

        await manager._run()

        for key, collector in collectors.items():
            assert collector._cached_device is None, f"{key} kept a stale handle"
    finally:
        for collector in collectors.values():
            collector.store.close()


async def test_a_normal_poll_keeps_handles(settings, tmp_path, monkeypatch):
    manager, collectors = build(settings, tmp_path)
    try:
        for collector in collectors.values():
            collector._cached_device = ("good", "handle")
            collector._next_attempt = 1e9

        async def brief_wait():
            manager._stop.set()
            return 0.01

        monkeypatch.setattr(manager, "_wait", brief_wait)
        await manager._run()

        for collector in collectors.values():
            assert collector._cached_device is not None, "a normal poll must not reset"
    finally:
        for collector in collectors.values():
            collector.store.close()
