"""Talking to the hardware: discovery, connection, reading and writing.

This is where the Bluetooth awkwardness lives. See docs/architecture.md for why the
collector waits for data rather than requesting it, and why every operation that holds
the shared radio is time-boxed.
"""

import asyncio
import importlib.util
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from bleak import BleakScanner

from .config import Settings
from .models import Control, DeviceKind
from .storage import TelemetryStore

log = logging.getLogger(__name__)


class DeviceCollector:
    # A BLE operation can hang forever waiting for an acknowledgement. The radio
    # lock is shared, so one stuck command freezes every device, not just its own.
    # These caps guarantee the lock is always given back.
    COMMAND_TIMEOUT = 20.0
    OPERATION_TIMEOUT = 120.0
    # How long to wait for the device to push its heartbeats after connecting, and
    # for a setting to read back. Class attributes so tests can shorten them.
    SETTLE_TIMEOUT = 30.0
    CONFIRM_TIMEOUT = 15.0

    def __init__(
        self,
        kind: DeviceKind,
        settings: Settings,
        store: TelemetryStore,
        radio_lock: asyncio.Lock,
    ) -> None:
        self.kind = kind
        self.settings = settings
        self.store = store
        self.latest: Any = None
        self.state = "not configured"
        self.error: str | None = None
        # The radio is shared: only one unit can hold a BLE connection at a time.
        self._refresh_lock = radio_lock
        self._device: Any = None
        self._eflib: Any = None
        self._cached_device: tuple[Any, Any] | None = None
        # A unit that is switched off should not cost a 10s scan every cycle.
        self._failures = 0
        self._next_attempt = 0.0
        self._in_flight = False
        # Whether this unit has ever answered. Changes what an absence means.
        self._seen_before = False

    async def refresh(self) -> None:
        if not self.settings.collector_ready:
            raise RuntimeError("Configure the local BLE collector first.")
        if self._in_flight:
            # A collection for THIS unit is already running, and its reading will be
            # as fresh as one started now, so wait for it rather than queueing a
            # second scan-connect-read cycle behind it. The lock alone cannot tell
            # us this any more: it is shared, so it may be held by the other unit.
            async with self._refresh_lock:
                return
        async with self._refresh_lock:
            self._in_flight = True
            try:
                async with asyncio.timeout(self.OPERATION_TIMEOUT):
                    await self._collect_once()
            except TimeoutError:
                self._cached_device = None
                raise RuntimeError(
                    f"Reading the {self.kind.label} timed out after "
                    f"{self.OPERATION_TIMEOUT:g}s."
                ) from None
            finally:
                self._in_flight = False

    def due(self, now: float) -> bool:
        """Whether this unit is worth trying again yet."""
        return self.settings.collector_ready and now >= self._next_attempt

    async def reset(self) -> None:
        """Throw away every Bluetooth handle this collector is holding.

        After the machine suspends, a CoreBluetooth link can survive in a half-open
        state: the unit still believes it is connected, so it stops advertising, and
        no amount of scanning will find it again. Dropping our side is the only
        lever available from here - the cross-platform helpers for closing a stale
        link are BlueZ-only.
        """
        log.info(
            "%s: resetting (held a device: %s, cached a handle: %s)",
            self.kind.label,
            self._device is not None,
            self._cached_device is not None,
        )
        if self._device is not None:
            with suppress(Exception):
                await self._device.disconnect()
            self._device = None
        self._cached_device = None
        self._failures = 0
        self._next_attempt = 0.0
        self.state = "reconnecting"

    def succeeded(self) -> None:
        self._failures = 0
        self._next_attempt = 0.0

    def failed(self, error: Exception, now: float) -> None:
        if not self._failures:
            log.warning("%s: %s", self.kind.label, error)
        self.state = "not found"
        self.error = str(error)
        self._failures += 1
        # 1x, 2x, 4x ... the poll interval, capped at five minutes, so a unit that
        # is switched off costs one scan occasionally instead of one every cycle.
        self._next_attempt = now + min(
            self.settings.poll_seconds * 2 ** (self._failures - 1), 300
        )

    def _load_eflib(self) -> Any:
        if self._eflib is not None:
            return self._eflib
        init_file = self.settings.eflib_root / "__init__.py"
        spec = importlib.util.spec_from_file_location(
            "eflib", init_file, submodule_search_locations=[str(init_file.parent)]
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load the EcoFlow BLE protocol library.")
        module = importlib.util.module_from_spec(spec)
        sys.modules["eflib"] = module
        spec.loader.exec_module(module)
        self._eflib = module
        return module

    async def _find_device(self, eflib: Any, use_cache: bool = True) -> tuple[Any, Any]:
        # Discovery costs a fixed 10s every cycle. Once the unit has been found and
        # connected to, the same handle works again, so keep it and skip the scan.
        if use_cache and self._cached_device is not None:
            return self._cached_device
        discoveries = await BleakScanner.discover(timeout=10, return_adv=True)
        # EcoFlow units carry their serial number in the advertisement, and the
        # library maps a serial to a device class. With more than one unit in range
        # that is the only way to tell them apart: the display name is renameable
        # and says nothing about the model.
        matches = []
        for item in discoveries.values():
            serial = eflib.sn_from_advertisement(item[1])
            if serial is None:
                continue
            device_class = eflib.device_class_from_sn(serial)
            if device_class is not None and device_class.__module__.endswith(
                self.kind.module_suffix
            ):
                matches.append(item)
        if matches:
            return max(matches, key=lambda item: item[1].rssi or -1000)
        # The radio is plainly working if it can see everything else, so say so:
        # this is the unit not advertising, not Bluetooth being broken.
        advice = (
            "Wake it, keep it in range, and close the EcoFlow phone app so it "
            "releases the Bluetooth connection."
        )
        if self._seen_before:
            advice += (
                " It was reachable earlier, so if it is switched on, a stale "
                "connection from this machine may be holding it silent - restarting "
                "the gateway clears that."
            )
        raise RuntimeError(
            f"No {self.kind.label} was found among {len(discoveries)} nearby Bluetooth "
            f"devices. {advice}"
        )

    async def _await_readings(self, device: Any) -> bool:
        """Wait for the device's heartbeats. True if everything expected arrived.

        This is a polling deadline rather than a cancellation scope: the values are
        pushed to us as properties, so there is no awaitable to cancel.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.SETTLE_TIMEOUT
        while True:
            if all(getattr(device, name, None) is not None for name in self.kind.settle_fields):
                return True
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(0.5)

    def _received_any(self, device: Any) -> bool:
        return any(
            getattr(device, name, None) is not None for name in self.kind.settle_fields
        )

    async def _open(self, eflib: Any, use_cache: bool) -> Any:
        ble_device, advertisement = await self._find_device(eflib, use_cache=use_cache)
        delta = eflib.NewDevice(ble_device, advertisement)
        if delta is None:
            raise RuntimeError("The selected Bluetooth device is not an EcoFlow DELTA.")
        self._device = delta
        delta.with_disabled_reconnect(True)
        self.state = "authenticating"
        await delta.connect(user_id=self.settings.user_id, max_attempts=1)
        await delta.wait_until_authenticated_or_error(raise_on_error=True)
        if not self._seen_before or self._failures:
            log.info("%s: connected (cached handle: %s)", self.kind.label, use_cache)
        self._cached_device = (ble_device, advertisement)
        self._seen_before = True
        return delta

    @asynccontextmanager
    async def _connected(self, use_cache: bool = True) -> AsyncIterator[Any]:
        self.state = "scanning"
        self.error = None
        eflib = self._load_eflib()
        try:
            delta = await self._open(eflib, use_cache=use_cache)
        except Exception:
            if not use_cache or self._cached_device is None:
                raise
            # A cached handle goes stale when the unit sleeps, moves out of range or
            # the OS drops the peripheral. Pay for one full scan rather than fail.
            self._cached_device = None
            self.state = "scanning"
            delta = await self._open(eflib, use_cache=False)
        try:
            yield delta
        finally:
            with suppress(Exception):
                await delta.disconnect()
            self._device = None

    @staticmethod
    def _attached(values: dict[str, float | None], index: int) -> float:
        """Whether an extra battery is really there, rather than merely flagged.

        battery_N_enabled reads true on this unit with nothing attached, so it is
        only believed when the pack also reports a voltage, a temperature or a
        non-zero level - the things a present pack actually sends.
        """
        if not values.get(f"battery_{index}_enabled"):
            return 0.0
        evidence = (
            values.get(f"battery_{index}_voltage"),
            values.get(f"battery_{index}_cell_temperature"),
            values.get(f"battery_{index}_battery_level"),
        )
        return 1.0 if any(value for value in evidence) else 0.0

    def _record(self, delta: Any) -> None:
        values = {
            name: self._value(delta, self.kind.sources.get(name, name))
            for name in self.kind.reading_fields
            if name not in self.kind.derived
        }
        for name in self.kind.derived:
            values[name] = self._attached(values, int(name.split("_")[1]))
        snapshot = self.kind.snapshot(
            timestamp=datetime.now(UTC).isoformat(), **values
        )
        self.latest = snapshot
        self.store.add(snapshot)

    async def _collect_once(self) -> None:
        if await self._attempt(use_cache=True):
            return
        # A cached handle can connect and authenticate and still deliver no
        # notifications at all. That raises nothing, so an empty read is the only
        # symptom - and without this the stale handle is reused forever, storing a
        # row of nulls every cycle.
        self._cached_device = None
        if await self._attempt(use_cache=False):
            return
        raise RuntimeError(
            f"The {self.kind.label} connected but sent no telemetry."
        )

    async def _attempt(self, use_cache: bool) -> bool:
        async with self._connected(use_cache=use_cache) as delta:
            self.state = "collecting"
            complete = await self._await_readings(delta)
            if not complete and not self._received_any(delta):
                return False
            self._record(delta)
            self.state = "latest reading complete"
            return True

    async def set_control(self, key: str, value: Any) -> bool:
        """Apply a setting, then read back what the unit actually adopted.

        Returns whether the device confirmed the new value. The command goes over
        the same single BLE connection the collector uses, so it takes the shared
        radio lock and can never overlap a reading.
        """
        control = self.kind.controls.get(key)
        if control is None:
            raise ValueError(f"'{key}' is not a controllable setting.")
        if not self.settings.collector_ready:
            raise RuntimeError("Configure the local BLE collector first.")
        # Check the value against the last reading before spending a ~20 second BLE
        # connection on something the unit would reject anyway.
        if self.latest is not None:
            self._validate(control, value, self.latest)
        async with self._refresh_lock:
            try:
                async with asyncio.timeout(self.OPERATION_TIMEOUT):
                    async with self._connected() as delta:
                        # Re-check against the live device, which is authoritative.
                        plain = self._validate(control, value, delta)
                        argument = self._argument(control, plain, delta)
                        self.state = "sending command"
                        async with asyncio.timeout(self.COMMAND_TIMEOUT):
                            await getattr(delta, control.method)(argument)
                        self.state = "collecting"
                        confirmed = await self._await_value(delta, control, argument)
                        await self._await_readings(delta)  # best effort before recording
                        self._record(delta)
                        self.state = "latest reading complete"
                        return confirmed
            except TimeoutError:
                self._cached_device = None
                self.state = "command timed out"
                raise RuntimeError(
                    f"The {self.kind.label} did not answer the command in time. "
                    "It may have been left in its previous state - check before retrying."
                ) from None

    def _bound(self, control: Control, which: str, device: Any) -> float | None:
        """Resolve a min/max that may be a literal or the name of a device field."""
        bound = getattr(control, which)
        if bound is None:
            return None
        if isinstance(bound, str):
            reported = getattr(device, bound, None)
            return None if reported is None else float(reported)
        return float(bound)

    def _validate(self, control: Control, value: Any, source: Any) -> Any:
        """Check a value against bounds read from `source`, which may be a live
        device or the last stored snapshot. Returns the plain Python value."""
        name = control.label or control.field
        if control.type == "switch":
            return bool(value)
        if control.type == "choice":
            try:
                chosen = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{value!r} is not a valid {name}.") from None
            if control.options is None or chosen not in control.options:
                raise ValueError(f"{value!r} is not a valid {name}.")
            return chosen
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{value!r} is not a number.") from None
        low = self._bound(control, "minimum", source)
        high = self._bound(control, "maximum", source)
        if low is not None and number < low:
            raise ValueError(f"{name} cannot go below {low:g}{control.unit}.")
        if high is not None and number > high:
            raise ValueError(f"{name} cannot go above {high:g}{control.unit}.")
        return number if control.step < 1 else int(number)

    @staticmethod
    def _argument(control: Control, plain: Any, device: Any) -> Any:
        """Convert a validated value into whatever the eflib method expects."""
        if control.type == "choice" and control.enum:
            # set_charger_mode wants the library's enum, not a bare int.
            return getattr(sys.modules[type(device).__module__], control.enum)(plain)
        return plain

    async def _await_value(self, device: Any, control: Control, expected: Any) -> bool:
        """Wait for the unit to report the setting in its new state.

        The property only changes when the next heartbeat carrying it arrives, so
        reading it straight after sending would return the old value and the
        dashboard would look like it had ignored the change.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.CONFIRM_TIMEOUT
        while loop.time() < deadline:
            current = getattr(device, control.field, None)
            if current is not None:
                if control.type == "switch" and bool(current) is bool(expected):
                    return True
                if control.type == "choice" and int(current) == int(expected):
                    return True
                if control.type == "number" and abs(float(current) - float(expected)) <= control.step / 2:
                    return True
            await asyncio.sleep(0.5)
        return False

    @staticmethod
    def _value(device: Any, name: str) -> float | None:
        # Three decimals, because cell voltages differ in the third one and their
        # spread - the imbalance - is the most useful health signal the pack gives.
        # Rounding to two collapsed 3.328/3.319 into 3.33/3.33, i.e. 0 mV.
        value = getattr(device, name, None)
        return round(float(value), 3) if value is not None else None

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "error": self.error,
            "configured": self.settings.collector_ready,
            "source": "local_ble",
            "key": self.kind.key,
            "label": self.kind.label,
            "controls": {
                key: {
                    "type": control.type,
                    "field": control.field,
                    "label": control.label,
                    "options": control.options,
                    "step": control.step,
                    "unit": control.unit,
                    "minimum": control.minimum,
                    "maximum": control.maximum,
                }
                for key, control in self.kind.controls.items()
            },
            "latest": asdict(self.latest) if self.latest else None,
        }


