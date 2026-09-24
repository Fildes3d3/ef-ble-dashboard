// What each card shows, and how a row becomes a widget.

import { BOOLEAN_FORMATS, chargerMode, fmt } from "./format.js";
import { isBusy, state } from "./store.js";
import { batteryIsReporting } from "./status.js";

export const DETAIL_GROUPS = [
  ["PORT OUTPUT", [
    ["AC outlets", "ac_output_power", fmt.w],
    ["12V / car", "dc_output_power", fmt.w],
    ["USB-C 1", "usbc_output_power", fmt.w],
    ["USB-C 2", "usbc2_output_power", fmt.w],
    ["USB-A 1", "usba_output_power", fmt.w],
    ["USB-A 2", "usba2_output_power", fmt.w],
    ["USB-A fast 1", "qc_usb1_output_power", fmt.w],
    ["USB-A fast 2", "qc_usb2_output_power", fmt.w],
  ]],
  ["BATTERY HEALTH", [
    ["Main pack level", "battery_level_main", fmt.pct],
    ["Cell temperature", "cell_temperature", fmt.c],
    ["Highest cell", "max_cell_voltage", fmt.v],
    ["Lowest cell", "min_cell_voltage", fmt.v],
    ["Cell imbalance", "cell_imbalance_mv", fmt.mv],
  ]],
  ["PORT SWITCHES", [
    ["AC outlets", "ac_ports", fmt.onOff, "ac_ports"],
    ["USB ports", "usb_ports", fmt.onOff, "usb_ports"],
    ["12V port", "dc_12v_port", fmt.onOff, "dc_12v_port"],
    ["Grid bypass", "grid_bypass", fmt.enabled],
  ]],
  ["AC DETAIL", [
    ["Input voltage", "ac_input_voltage", fmt.v],
    ["Input current", "ac_input_current", fmt.a],
    ["Output voltage", "ac_output_voltage", fmt.v],
    ["Output current", "ac_output_current", fmt.a],
  ]],
  ["DC DETAIL", [
    ["Solar / XT60 voltage", "dc_input_voltage", fmt.v],
    ["Solar / XT60 current", "dc_input_current", fmt.a],
    ["12V rail voltage", "dc12v_output_voltage", fmt.v],
    ["12V rail current", "dc12v_output_current", fmt.a],
  ]],
  ["CHARGING SETTINGS", [
    ["AC charging", "ac_charging", fmt.enabled, "ac_charging"],
    ["AC charge speed", "ac_charging_speed", fmt.w, "ac_charging_speed"],
    ["Charge limit low", "battery_charge_limit_min", fmt.pct, "battery_charge_limit_min"],
    ["Charge limit high", "battery_charge_limit_max", fmt.pct, "battery_charge_limit_max"],
    ["Energy backup", "energy_backup", fmt.enabled, "energy_backup"],
    ["Backup reserve", "energy_backup_battery_level", fmt.pct, "energy_backup_battery_level"],
  ]],
];

export const extraBatteryGroup = (index) => [`EXTRA BATTERY ${index}`, [
  ["Level", `battery_${index}_battery_level`, fmt.pct],
  ["Voltage", `battery_${index}_voltage`, fmt.v],
  ["Cell temperature", `battery_${index}_cell_temperature`, fmt.c],
  ["Highest cell", `battery_${index}_max_cell_voltage`, fmt.v],
  ["Lowest cell", `battery_${index}_min_cell_voltage`, fmt.v],
]];

// battery_N_attached is derived by the collector, which weighs the unreliable

export const ALT_GROUPS = [
  ["CHARGE STATE", [
    ["Mode", "charger_mode", chargerMode, "charger_mode"],
    ["Charger", "charger_open", fmt.enabled, "charger_open"],
    ["Charge power", "dc_power", fmt.w],
    ["Emergency reverse charge", "emergency_reverse_charging", fmt.enabled, "emergency_reverse_charging"],
  ]],
  ["VEHICLE SIDE", [
    ["Battery voltage", "car_battery_voltage", fmt.v],
    ["Start threshold", "start_voltage", fmt.v, "start_voltage"],
  ]],
  ["PACK SIDE", [
    ["Pack level", "battery_level", fmt.pct],
    ["Pack temperature", "battery_temperature", fmt.c],
  ]],
  ["LIMITS", [
    ["Power limit", "power_limit", fmt.w, "power_limit"],
    ["Charge current limit", "charging_current_limit", fmt.a, "charging_current_limit"],
    ["Reverse current limit", "reverse_charging_current_limit", fmt.a, "reverse_charging_current_limit"],
  ]],
];

export function buildControl(spec, key, label, value, busy, source) {
  const unavailable = value == null || busy;
  const reason = value == null
    ? "Not reported in this reading."
    : busy ? "Bluetooth is busy - try again in a moment." : "";

  if (spec.type === "switch") {
    const button = document.createElement("button");
    button.className = "toggle";
    button.textContent = value == null ? "—" : (value ? "On" : "Off");
    button.disabled = unavailable;
    button.title = reason || `Turn ${label} ${value ? "off" : "on"}.`;
    button.addEventListener("click", () =>
      state.onControl(key, label, !value, `Turning ${label} ${value ? "off" : "on"}`));
    return button;
  }

  if (spec.type === "choice") {
    const select = document.createElement("select");
    select.className = "control-select";
    select.disabled = unavailable;
    select.title = reason || `Change ${label}.`;
    for (const [option, text] of Object.entries(spec.options || {})) {
      const item = document.createElement("option");
      item.value = option;
      item.textContent = text;
      if (value != null && Number(option) === Number(value)) item.selected = true;
      select.append(item);
    }
    select.addEventListener("change", () => {
      const text = select.options[select.selectedIndex].textContent;
      state.onControl(key, label, Number(select.value), `Setting ${label} to ${text}`);
    });
    return select;
  }

  // number -> a slider, so the bounds the unit reports are visible rather than
  // discovered by having a value rejected.
  const bound = (limit) =>
    typeof limit === "string" ? (source || {})[limit] ?? null : limit;
  const low = bound(spec.minimum);
  const high = bound(spec.maximum);
  const step = spec.step ?? 1;
  const decimals = step < 1 ? 1 : 0;
  const show = (v) => v == null ? "—" : `${Number(v).toFixed(decimals)}${spec.unit}`;

  const wrapper = document.createElement("div");
  wrapper.className = "slider";

  const head = document.createElement("div");
  head.className = "slider-head";
  const current = document.createElement("strong");
  current.textContent = show(value);
  head.append(current);

  const body = document.createElement("div");
  body.className = "slider-body";
  const lowLabel = document.createElement("span");
  lowLabel.className = "slider-bound";
  lowLabel.textContent = show(low);
  const highLabel = document.createElement("span");
  highLabel.className = "slider-bound";
  highLabel.textContent = show(high);

  const input = document.createElement("input");
  input.type = "range";
  input.step = step;
  if (low != null) input.min = low;
  if (high != null) input.max = high;
  input.value = value == null ? (low ?? 0) : value;
  input.disabled = unavailable || low == null || high == null;
  input.title = reason || `Drag to change ${label}.`;
  // Track while dragging, but only send once the handle is released.
  input.addEventListener("input", () => { current.textContent = show(input.value); });
  input.addEventListener("change", () => {
    const next = Number(input.value);
    if (!Number.isFinite(next) || next === value) return;
    state.onControl(key, label, next, `Setting ${label} to ${show(next)}`);
  });

  body.append(lowLabel, input, highLabel);
  wrapper.append(head, body);
  return wrapper;
}

export function renderGroups(containerId, groups, snapshot, values = null, controls = null) {
  const grid = document.querySelector(`#${containerId}`);
  grid.replaceChildren();
  const source = values ?? snapshot ?? {};
  for (const [title, rows] of groups) {
    const card = document.createElement("article");
    card.className = "detail-card";
    const heading = document.createElement("p");
    heading.className = "card-label";
    heading.textContent = title;
    card.append(heading);
    for (const [label, key, format, control] of rows) {
      const value = snapshot == null ? null : (source[key] ?? null);
      const row = document.createElement("div");
      const classes = ["detail-row"];
      // A dash means the unit did not report the field in this reading, which is
      // not the same as a zero, so it stays a dash - just a clearly muted one.
      if (value == null) classes.push("missing");
      else if (BOOLEAN_FORMATS.has(format) && !value) classes.push("off");
      row.className = classes.join(" ");
      if (value == null) row.title = "Not reported in this reading.";
      const name = document.createElement("span");
      name.textContent = label;
      const spec = control ? (controls || {})[control] : null;
      const busy = isBusy();
      const reading = spec
        ? buildControl(spec, control, label, value, busy, source)
        : Object.assign(document.createElement("strong"), { textContent: format(value) });
      if (!spec) reading.textContent = format(value);
      if (spec && spec.type === "number") row.classList.add("has-slider");
      row.append(name, reading);
      card.append(row);
    }
    grid.append(card);
  }
}
