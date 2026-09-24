"""Control validation. These bounds are what stops a slider writing nonsense."""

import asyncio

import pytest

from app.collector import DeviceCollector
from app.devices import ALTERNATOR, DELTA2


class Reading:
    """Stands in for a stored snapshot or a live device: it just holds bounds."""

    def __init__(self, **values):
        self._values = values

    def __getattr__(self, name):
        return self._values.get(name)


def make(kind, store, settings):
    return DeviceCollector(kind, settings, store, asyncio.Lock())


def test_switch_coerces_to_bool(store, settings):
    control = DELTA2.controls["ac_ports"]
    assert make(DELTA2, store, settings)._validate(control, 1, Reading()) is True


def test_choice_rejects_a_value_outside_the_options(store, settings):
    control = ALTERNATOR.controls["charger_mode"]
    collector = make(ALTERNATOR, store, settings)
    assert collector._validate(control, 2, Reading()) == 2
    with pytest.raises(ValueError, match="not a valid Mode"):
        collector._validate(control, 9, Reading())


def test_number_is_bounded_by_what_the_device_reports(store, settings):
    """The ceiling is a field name, resolved from the reading - not a constant."""
    control = ALTERNATOR.controls["power_limit"]
    collector = make(ALTERNATOR, store, settings)
    reading = Reading(power_max=100.0)

    assert collector._validate(control, 50, reading) == 50
    with pytest.raises(ValueError, match="cannot go above 100W"):
        collector._validate(control, 999, reading)
    with pytest.raises(ValueError, match="cannot go below 0W"):
        collector._validate(control, -1, reading)


def test_charge_limits_bound_each_other(store, settings):
    """The low limit may not exceed the high one, and vice versa."""
    collector = make(DELTA2, store, settings)
    reading = Reading(battery_charge_limit_min=5.0, battery_charge_limit_max=95.0)

    low = DELTA2.controls["battery_charge_limit_min"]
    high = DELTA2.controls["battery_charge_limit_max"]

    with pytest.raises(ValueError, match="cannot go above 95%"):
        collector._validate(low, 99, reading)
    with pytest.raises(ValueError, match="cannot go below 5%"):
        collector._validate(high, 2, reading)
    assert collector._validate(low, 20, reading) == 20
    assert collector._validate(high, 80, reading) == 80


def test_non_numeric_input_is_rejected_clearly(store, settings):
    control = ALTERNATOR.controls["power_limit"]
    with pytest.raises(ValueError, match="not a number"):
        make(ALTERNATOR, store, settings)._validate(control, "abc", Reading(power_max=100.0))


def test_a_float_step_keeps_decimals(store, settings):
    """Start threshold moves in 0.1 V steps and must not be truncated to an int."""
    control = ALTERNATOR.controls["start_voltage"]
    reading = Reading(start_voltage_min=11.0, start_voltage_max=31.0)
    assert make(ALTERNATOR, store, settings)._validate(control, 13.5, reading) == 13.5


def test_an_unbounded_reading_does_not_block_the_write(store, settings):
    """If the device has not reported its ceiling yet, do not invent one."""
    control = ALTERNATOR.controls["power_limit"]
    assert make(ALTERNATOR, store, settings)._validate(control, 999, Reading()) == 999


def test_read_only_settings_are_absent_from_the_registry():
    for forbidden in ("disable_grid_bypass", "power_max", "battery_level"):
        assert forbidden not in DELTA2.controls
        assert forbidden not in ALTERNATOR.controls
