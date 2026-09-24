"""Domain models.

The snapshot dataclasses are the single source of truth for what is collected: the
SQLite schema, its migration and the insert statement are all generated from them.
"""

from dataclasses import dataclass, fields


@dataclass
class Snapshot:
    """Every value the DELTA 2 reports that is worth keeping over time.

    Field names match the eflib device attributes so the collector can map them
    automatically; FIELD_SOURCES holds the only exceptions. Adding a field here is
    enough - the SQLite schema, the migration and the insert all follow from it.
    """

    timestamp: str

    # Charge state and pack health
    battery_level: float | None = None
    battery_level_main: float | None = None
    battery_voltage: float | None = None
    cell_temperature: float | None = None
    max_cell_voltage: float | None = None
    min_cell_voltage: float | None = None

    # Totals
    input_power: float | None = None
    output_power: float | None = None
    solar_power: float | None = None

    # AC side
    ac_input_power: float | None = None
    ac_input_voltage: float | None = None
    ac_input_current: float | None = None
    ac_output_power: float | None = None
    ac_output_voltage: float | None = None
    ac_output_current: float | None = None

    # DC side
    dc_input_voltage: float | None = None
    dc_input_current: float | None = None
    dc_output_power: float | None = None
    dc12v_output_voltage: float | None = None
    dc12v_output_current: float | None = None

    # Per-port draw
    usbc_output_power: float | None = None
    usbc2_output_power: float | None = None
    usba_output_power: float | None = None
    usba2_output_power: float | None = None
    qc_usb1_output_power: float | None = None
    qc_usb2_output_power: float | None = None

    # Port switches
    ac_ports: float | None = None
    usb_ports: float | None = None
    dc_12v_port: float | None = None

    # Charging configuration
    ac_charging: float | None = None
    ac_charging_speed: float | None = None
    ac_charging_speed_min: float | None = None
    ac_charging_power_max: float | None = None
    battery_charge_limit_min: float | None = None
    battery_charge_limit_max: float | None = None
    energy_backup: float | None = None
    energy_backup_battery_level: float | None = None
    disable_grid_bypass: float | None = None

    # Attached extra batteries
    battery_1_enabled: float | None = None
    battery_1_battery_level: float | None = None
    battery_1_voltage: float | None = None
    battery_1_cell_temperature: float | None = None
    battery_1_max_cell_voltage: float | None = None
    battery_1_min_cell_voltage: float | None = None
    battery_2_enabled: float | None = None
    battery_2_battery_level: float | None = None
    battery_2_voltage: float | None = None
    battery_2_cell_temperature: float | None = None
    battery_2_max_cell_voltage: float | None = None
    battery_2_min_cell_voltage: float | None = None
    # Derived, not read from the unit: battery_N_enabled stays true on this DELTA 2
    # with no pack attached, so it cannot be trusted on its own.
    battery_1_attached: float | None = None
    battery_2_attached: float | None = None

    # Estimates
    remaining_time_charging: float | None = None
    remaining_time_discharging: float | None = None


@dataclass
class AlternatorSnapshot:
    """Everything the Alternator Charger reports.

    It sends a single protobuf (DisplayPropertyUpload), so unlike the DELTA 2 the
    fields all arrive together rather than across several heartbeats.
    """

    timestamp: str

    # What it is doing
    charger_mode: float | None = None
    charger_open: float | None = None
    dc_power: float | None = None

    # The vehicle side
    car_battery_voltage: float | None = None
    start_voltage: float | None = None
    start_voltage_min: float | None = None
    start_voltage_max: float | None = None

    # The pack side
    battery_level: float | None = None
    battery_temperature: float | None = None

    # Limits and ceilings
    power_limit: float | None = None
    power_max: float | None = None
    charging_current_limit: float | None = None
    charging_current_max: float | None = None
    reverse_charging_current_limit: float | None = None
    reverse_charging_current_max: float | None = None
    emergency_reverse_charging: float | None = None


@dataclass(frozen=True)
class Control:
    """A writable setting: what to call, and how to read back what happened."""

    field: str                       # snapshot/device attribute reflecting the change
    method: str                      # eflib coroutine to invoke
    type: str                        # "switch" | "choice" | "number"
    label: str = ""
    options: dict[int, str] | None = None     # for "choice"
    enum: str | None = None          # enum class in the device module, if it wants one
    minimum: str | float | None = None        # literal, or the field holding the bound
    maximum: str | float | None = None
    step: float = 1.0
    unit: str = ""


@dataclass(frozen=True)
class DeviceKind:
    """Everything that differs between the units this gateway can read."""

    key: str
    label: str
    table: str
    module_suffix: str
    snapshot: type
    sources: dict[str, str]
    derived: frozenset[str]
    settle_fields: tuple[str, ...]
    controls: dict[str, Control]

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(field.name for field in fields(self.snapshot))

    @property
    def reading_fields(self) -> tuple[str, ...]:
        return tuple(name for name in self.fields if name != "timestamp")


