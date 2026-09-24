// The DOM layer. Decisions live in status.js; this applies them.

import { drawChart } from "./chart.js";
import { chargerMode, fmt, number, time } from "./format.js";
import { ALT_GROUPS, DETAIL_GROUPS, extraBatteryGroup, renderGroups } from "./groups.js";
import {
  batteryIsReporting, batteryMessage, connectionState, freshness, refreshButtonState,
} from "./status.js";
import { isBusy, state } from "./store.js";

export function setText(id, value) {
  document.querySelector(`#${id}`).textContent = value;
}

/** Says how old the readings are, and marks them when they are not current. */
export function showFreshness(status) {
  const { stale, text } = freshness(status);
  setText("status-note", text);
  document.querySelector("#status-note").classList.toggle("stale", stale);
  for (const panel of document.querySelectorAll("#panel-delta2, #panel-alternator")) {
    if (!panel.hidden) panel.classList.toggle("has-stale-readings", stale);
  }
}


export function connectionPill(status) {
  const { text, modifier } = connectionState(status);
  const pill = document.querySelector("#connection-pill");
  pill.textContent = text;
  pill.className = `connection-pill ${modifier}`;
}

export function updateRefreshButton() {
  const button = document.querySelector("#refresh-button");
  const { label, hint, disabled } = refreshButtonState(state.pendingAction, state.lastStatus);
  button.textContent = label;
  button.title = hint;
  button.disabled = disabled;
}

export function render(snapshot, status) {
  state.lastStatus = status;
  updateRefreshButton();
  connectionPill(status);
  if (!snapshot) {
    setText("status-note", status.error || "Waiting for the first local BLE reading.");
    return;
  }
  setText("battery-level", number(snapshot.battery_level));
  document.querySelector("#panel-delta2 .battery-ring").style.setProperty("--level", snapshot.battery_level ?? 0);
  setText("battery-message", batteryMessage(snapshot));
  setText("battery-meta", `${number(snapshot.battery_voltage, " V")} battery voltage`);
  setText("solar-power", number(snapshot.solar_power, " W"));
  setText("ac-input-power", number(snapshot.ac_input_power, " W"));
  setText("output-power", number(snapshot.output_power, " W"));
  setText("input-power", number(snapshot.input_power));
  setText("battery-voltage", number(snapshot.battery_voltage));
  setText("time-left", time(snapshot.remaining_time_discharging));
  setText("charge-time", snapshot.input_power > 0 ? time(snapshot.remaining_time_charging) : "—");
  renderDetail(snapshot);
  if (!state.pendingAction) showFreshness(status);
}

export function renderDetail(snapshot) {
  state.lastSnapshot = snapshot;
  if (!snapshot) return renderGroups("detail-grid", DETAIL_GROUPS, null, null, state.lastStatus.controls);

  const values = { ...snapshot };
  values.cell_imbalance_mv =
    snapshot.max_cell_voltage == null || snapshot.min_cell_voltage == null
      ? null
      : (snapshot.max_cell_voltage - snapshot.min_cell_voltage) * 1000;
  values.grid_bypass = snapshot.disable_grid_bypass == null
    ? null
    : (snapshot.disable_grid_bypass ? 0 : 1);

  const groups = [...DETAIL_GROUPS];
  for (const index of [1, 2]) if (batteryIsReporting(snapshot, index)) groups.push(extraBatteryGroup(index));
  renderGroups("detail-grid", groups, snapshot, values, state.lastStatus.controls);
}

export function renderAlternator(snapshot, status) {
  const button = document.querySelector("#alt-refresh-button");
  const busy = isBusy();
  button.disabled = busy;
  button.textContent = refreshButtonState(state.pendingAction, status, "alt-refresh").label;

  if (!snapshot) {
    setText("alt-mode", status.error ? "Not reachable" : "Waiting for telemetry");
    setText("alt-meta", status.error || "Charger on the XT150 port");
    renderGroups("alt-detail-grid", ALT_GROUPS, null, null, status.controls);
    return;
  }
  setText("alt-battery-level", number(snapshot.battery_level));
  document.querySelector("#panel-alternator .battery-ring")
    .style.setProperty("--level", snapshot.battery_level ?? 0);
  setText("alt-mode", chargerMode(snapshot.charger_mode));
  setText("alt-meta", `${fmt.v(snapshot.car_battery_voltage)} at the vehicle battery`);
  setText("alt-dc-power", fmt.w(snapshot.dc_power));
  setText("alt-car-voltage", fmt.v(snapshot.car_battery_voltage));
  setText("alt-start-voltage", fmt.v(snapshot.start_voltage));
  renderGroups("alt-detail-grid", ALT_GROUPS, snapshot, null, status.controls);
}
