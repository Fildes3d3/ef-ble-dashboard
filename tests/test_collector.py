"""Regression tests for faults that actually occurred against real hardware."""

import asyncio

import pytest

from app.collector import DeviceCollector
from app.devices import ALTERNATOR, DELTA2


class FakeDevice:
    """A device that reports whatever it is handed, and nothing else."""

    def __init__(self, **reported):
        self._reported = reported

    def __getattr__(self, name):
        return self._reported.get(name)

    async def disconnect(self):
        pass


def make(kind, store, settings):
    collector = DeviceCollector(kind, settings, store, asyncio.Lock())
    # Real hardware needs 30s to push everything; a fake device needs none of it.
    collector.SETTLE_TIMEOUT = 0.05
    collector.CONFIRM_TIMEOUT = 0.05
    return collector


# --- precision -------------------------------------------------------------

def test_value_keeps_three_decimals(store, settings):
    """Two decimals collapsed 3.328/3.319 into 3.33/3.33, hiding cell imbalance."""
    collector = make(DELTA2, store, settings)
    device = FakeDevice(max_cell_voltage=3.328, min_cell_voltage=3.319)
    high = collector._value(device, "max_cell_voltage")
    low = collector._value(device, "min_cell_voltage")
    assert high != low
    assert round((high - low) * 1000) == 9


def test_value_of_a_missing_field_is_none_not_zero(store, settings):
    collector = make(DELTA2, store, settings)
    assert collector._value(FakeDevice(), "battery_level") is None


# --- derived "attached" ----------------------------------------------------

@pytest.mark.parametrize(
    "values,expected",
    [
        ({"battery_1_enabled": 0}, 0.0),
        # The real case: a charger on the XT150 port sets the flag but sends no data.
        ({"battery_1_enabled": 1}, 0.0),
        ({"battery_1_enabled": 1, "battery_1_battery_level": 0.0}, 0.0),
        ({"battery_1_enabled": 1, "battery_1_voltage": 52.1}, 1.0),
        ({"battery_1_enabled": 1, "battery_1_cell_temperature": 24}, 1.0),
        ({"battery_1_enabled": 1, "battery_1_battery_level": 55.0}, 1.0),
    ],
)
def test_attached_needs_evidence_not_just_the_flag(store, values, expected, settings):
    collector = make(DELTA2, store, settings)
    assert collector._attached(values, 1) == expected


# --- the overnight failure -------------------------------------------------

async def test_a_silent_cached_handle_is_dropped_and_rescanned(alternator_store, settings):
    """After a system sleep the cached handle connected, authenticated, and sent
    nothing. That raises no exception, so only an empty read reveals it."""
    collector = make(ALTERNATOR, alternator_store, settings)
    collector._eflib = object()
    collector._cached_device = ("stale", "handle")
    attempts = []

    async def fake_open(eflib, use_cache):
        attempts.append(use_cache)
        return FakeDevice() if use_cache else FakeDevice(car_battery_voltage=13.9)

    collector._open = fake_open
    await collector._collect_once()

    assert attempts == [True, False], "should retry with a fresh scan"
    assert collector._cached_device is None, "stale handle should be dropped"
    assert collector.latest.car_battery_voltage == 13.9


async def test_a_genuinely_silent_device_raises_rather_than_storing_nulls(
    alternator_store, settings
):
    collector = make(ALTERNATOR, alternator_store, settings)
    collector._eflib = object()

    async def always_silent(eflib, use_cache):
        return FakeDevice()

    collector._open = always_silent
    with pytest.raises(RuntimeError, match="sent no telemetry"):
        await collector._collect_once()
    assert alternator_store.history() == [], "no row should be written"


# --- backoff ---------------------------------------------------------------

def test_backoff_grows_then_resets(store, settings):
    collector = make(DELTA2, store, settings)
    assert collector.due(now=0.0)

    collector.failed(RuntimeError("not found"), now=0.0)
    first = collector._next_attempt
    collector.failed(RuntimeError("not found"), now=0.0)
    second = collector._next_attempt
    assert second > first, "backoff should grow"
    assert not collector.due(now=0.0)

    collector.succeeded()
    assert collector.due(now=0.0), "a success should clear the backoff"


def test_backoff_is_capped(store, settings):
    collector = make(DELTA2, store, settings)
    for _ in range(20):
        collector.failed(RuntimeError("still absent"), now=0.0)
    assert collector._next_attempt <= 300.0


# --- recovering from a machine suspend ------------------------------------

async def test_reset_drops_every_handle(alternator_store, settings):
    """After a suspend a CoreBluetooth link can survive half-open: the unit thinks
    it is still connected and stops advertising, so scanning never finds it."""
    collector = make(ALTERNATOR, alternator_store, settings)
    disconnected = []

    class Lingering:
        async def disconnect(self):
            disconnected.append(True)

    collector._device = Lingering()
    collector._cached_device = ("stale", "handle")
    collector.failed(RuntimeError("not found"), now=0.0)

    await collector.reset()

    assert disconnected == [True], "the lingering link must be dropped"
    assert collector._device is None
    assert collector._cached_device is None
    assert collector.due(now=0.0), "backoff should not delay the first attempt after a wake"


async def test_reset_survives_a_device_that_cannot_disconnect(alternator_store, settings):
    collector = make(ALTERNATOR, alternator_store, settings)

    class Broken:
        async def disconnect(self):
            raise OSError("link already gone")

    collector._device = Broken()
    await collector.reset()
    assert collector._device is None


def test_absence_reads_differently_once_a_device_has_answered(store, settings):
    collector = make(DELTA2, store, settings)
    assert collector._seen_before is False
