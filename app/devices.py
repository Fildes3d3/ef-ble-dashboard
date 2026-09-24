"""The device registry: everything that differs between the units we can read."""

from .models import AlternatorSnapshot, Control, DeviceKind, Snapshot

DELTA2 = DeviceKind(
    key="delta2",
    label="DELTA 2",
    table="snapshots",
    module_suffix="devices.delta2",
    snapshot=Snapshot,
    # Snapshot field -> eflib attribute, where the two names differ.
    sources={"solar_power": "xt60_input_power"},
    # Computed in the collector rather than read off the device.
    derived=frozenset({"battery_1_attached", "battery_2_attached"}),
    # One representative field per heartbeat the DELTA 2 sends. The inverter's
    # arrives least often: a fixed 8 second wait missed it in roughly 40% of
    # readings, which surfaced as empty AC values on the dashboard.
    settle_fields=(
        "battery_level",
        "input_power",
        "battery_voltage",
        "dc_input_voltage",
        "ac_output_voltage",
    ),
    # The writable settings. Grid bypass is deliberately left out (see below).
    controls={
        "ac_ports": Control("ac_ports", "enable_ac_ports", "switch", "AC outlets"),
        "usb_ports": Control("usb_ports", "enable_usb_ports", "switch", "USB ports"),
        "dc_12v_port": Control("dc_12v_port", "enable_dc_12v_port", "switch", "12V port"),
        "ac_charging": Control("ac_charging", "enable_ac_charging", "switch", "AC charging"),
        "ac_charging_speed": Control(
            "ac_charging_speed", "set_ac_charging_speed", "number", "AC charge speed",
            minimum="ac_charging_speed_min", maximum="ac_charging_power_max", unit="W",
        ),
        "battery_charge_limit_min": Control(
            "battery_charge_limit_min", "set_battery_charge_limit_min", "number",
            "Charge limit low", minimum=0, maximum="battery_charge_limit_max", unit="%",
        ),
        "battery_charge_limit_max": Control(
            "battery_charge_limit_max", "set_battery_charge_limit_max", "number",
            "Charge limit high", minimum="battery_charge_limit_min", maximum=100, unit="%",
        ),
        "energy_backup": Control(
            "energy_backup", "enable_energy_backup", "switch", "Energy backup"
        ),
        "energy_backup_battery_level": Control(
            "energy_backup_battery_level", "set_energy_backup_battery_level", "number",
            "Backup reserve",
            minimum="battery_charge_limit_min", maximum="battery_charge_limit_max",
            unit="%",
        ),
        # disable_grid_bypass stays read-only: the library ships it disabled by
        # default, and its inverted sense makes a mis-click easy to misread.
    },
)

ALTERNATOR = DeviceKind(
    key="alternator",
    label="DC to DC",
    table="alternator_snapshots",
    module_suffix="devices.alternator_charger",
    snapshot=AlternatorSnapshot,
    sources={},
    derived=frozenset(),
    # A single protobuf carries the lot, so one field is enough to know it landed.
    settle_fields=("car_battery_voltage",),
    controls={
        "charger_open": Control(
            "charger_open", "enable_charger_open", "switch", "Charger"
        ),
        "charger_mode": Control(
            "charger_mode", "set_charger_mode", "choice", "Mode",
            options={
                0: "Idle",
                1: "Charging while driving",
                2: "Battery maintenance",
                3: "Reverse charge",
            },
            enum="ChargerMode",
        ),
        "power_limit": Control(
            "power_limit", "set_power_limit", "number", "Power limit",
            minimum=0, maximum="power_max", unit="W",
        ),
        "start_voltage": Control(
            "start_voltage", "set_battery_voltage", "number", "Start threshold",
            minimum="start_voltage_min", maximum="start_voltage_max",
            step=0.1, unit="V",
        ),
        "charging_current_limit": Control(
            "charging_current_limit", "set_device_battery_current_charge_limit",
            "number", "Charge current limit",
            minimum=0, maximum="charging_current_max", unit="A",
        ),
        "reverse_charging_current_limit": Control(
            # Note the library's spelling of this method ("curent").
            "reverse_charging_current_limit", "set_car_battery_curent_charge_limit",
            "number", "Reverse current limit",
            minimum=0, maximum="reverse_charging_current_max", unit="A",
        ),
        "emergency_reverse_charging": Control(
            "emergency_reverse_charging", "enable_emergency_reverse_charging",
            "switch", "Emergency reverse charge",
        ),
    },
)

DEVICE_KINDS = {kind.key: kind for kind in (DELTA2, ALTERNATOR)}


