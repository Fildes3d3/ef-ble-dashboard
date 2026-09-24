// Decisions about what the dashboard should say. Pure: given a reading, return
// text. The DOM work lives in views.js.

import { BUSY_STATES } from "./store.js";

export function batteryMessage(snapshot) {
  const input = snapshot.input_power ?? 0;
  const output = snapshot.output_power ?? 0;
  if (input === 0 && output === 0) return "Idle";
  if (input > output) return "Charging";
  if (output > input) return "Powering your van";
  return "Passing power through";
}

// The collector is mid-read for a good part of every poll cycle, and a click then
// only waits for the reading already in flight. Reflecting that in the button is

// battery_N_attached is derived by the collector, which weighs the unreliable
// battery_N_enabled flag against whether the pack actually reports anything.
export function batteryIsReporting(snapshot, index) {
  return Boolean(snapshot[`battery_${index}_attached`]);
}

/**
 * What the Refresh button should show.
 *
 * The collector is mid-read for a good part of every poll cycle, and a click then
 * only waits for the reading already in flight. Reflecting that is more honest than
 * letting the button look clickable and then appear to hang.
 */
export function refreshButtonState(pendingAction, status, ownAction = "refresh") {
  if (pendingAction === ownAction) {
    return { label: "Refreshing…", hint: "Reading the device over Bluetooth now.", disabled: true };
  }
  if (pendingAction) {
    return { label: "Working…", hint: "A command is in flight over Bluetooth.", disabled: true };
  }
  if (!status.configured) {
    return { label: "Unavailable", hint: "The local BLE collector is not configured yet.", disabled: true };
  }
  if (BUSY_STATES.has(status.state)) {
    return { label: "Updating…", hint: "A reading is already in progress over Bluetooth.", disabled: true };
  }
  return { label: "Refresh", hint: "Read the device now over Bluetooth.", disabled: false };
}

/** Text and CSS class for the connection pill. */
export function connectionState(status) {
  const connected = status.state === "latest reading complete";
  return {
    text: connected ? "Local BLE ready" : status.state,
    modifier: connected ? "connected" : status.error ? "error" : "",
  };
}

/** How long ago a reading was taken, in words. */
export function ageInWords(milliseconds) {
  const minutes = Math.floor(milliseconds / 60000);
  if (minutes < 1) return "just now";
  if (minutes === 1) return "1 minute ago";
  if (minutes < 60) return `${minutes} minutes ago`;
  const hours = Math.round(minutes / 60);
  if (hours === 1) return "1 hour ago";
  if (hours < 48) return `${hours} hours ago`;
  return `${Math.round(hours / 24)} days ago`;
}

/**
 * What to say beneath the readings.
 *
 * A device that has gone off keeps its last snapshot on screen. Without saying how
 * old those numbers are, a three-hour-old battery level looks like the current one -
 * the same mistake as drawing a missing reading as zero.
 */
export function freshness(status, now = Date.now()) {
  if (!status.latest) {
    return { stale: true, text: status.error || "Waiting for the first local BLE reading." };
  }
  const age = now - new Date(status.latest.timestamp).getTime();
  const reachable = !status.error;
  if (reachable && age < 5 * 60000) {
    const at = new Date(status.latest.timestamp)
      .toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return { stale: false, text: `Updated ${at} · local BLE only · no EcoFlow cloud data is used.` };
  }
  const when = ageInWords(age);
  if (!reachable) {
    return { stale: true, text: `Not reachable. These readings are from ${when}. ${status.error}` };
  }
  return { stale: true, text: `These readings are from ${when}.` };
}
