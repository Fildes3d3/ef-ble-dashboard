import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  ageInWords, batteryIsReporting, batteryMessage, connectionState, freshness,
  refreshButtonState,
} from "../../static/js/status.js";

describe("batteryMessage", () => {
  it("does not claim to be charging when nothing is flowing", () => {
    // The original bug: `output > input ? ... : "Charging and ready"` made an idle
    // unit report that it was charging.
    assert.equal(batteryMessage({ input_power: 0, output_power: 0 }), "Idle");
  });
  it("names the direction power is flowing", () => {
    assert.equal(batteryMessage({ input_power: 400, output_power: 0 }), "Charging");
    assert.equal(batteryMessage({ input_power: 0, output_power: 120 }), "Powering your van");
  });
  it("recognises passthrough", () => {
    assert.equal(
      batteryMessage({ input_power: 200, output_power: 200 }), "Passing power through");
  });
  it("treats missing readings as idle rather than guessing", () => {
    assert.equal(batteryMessage({ input_power: null, output_power: null }), "Idle");
  });
});

describe("batteryIsReporting", () => {
  it("believes the derived field, not the raw flag", () => {
    assert.equal(batteryIsReporting({ battery_1_attached: 1 }, 1), true);
    assert.equal(batteryIsReporting({ battery_1_attached: 0 }, 1), false);
    assert.equal(batteryIsReporting({}, 2), false);
  });
});

describe("refreshButtonState", () => {
  const ready = { configured: true, state: "latest reading complete" };

  it("is clickable when the radio is free", () => {
    const { label, disabled } = refreshButtonState(null, ready);
    assert.equal(label, "Refresh");
    assert.equal(disabled, false);
  });

  it("says what it is doing while its own command runs", () => {
    assert.equal(refreshButtonState("refresh", ready).label, "Refreshing…");
  });

  it("shows another action is in flight rather than looking clickable", () => {
    const { label, disabled } = refreshButtonState("ac_ports", ready);
    assert.equal(label, "Working…");
    assert.equal(disabled, true);
  });

  it("reflects the collector's own poll", () => {
    for (const state of ["scanning", "authenticating", "collecting"]) {
      const result = refreshButtonState(null, { configured: true, state });
      assert.equal(result.label, "Updating…");
      assert.equal(result.disabled, true);
    }
  });

  it("stays clickable while reconnecting, when a retry is most useful", () => {
    const result = refreshButtonState(null, { configured: true, state: "reconnecting" });
    assert.equal(result.disabled, false);
  });

  it("says so when the collector is not configured", () => {
    const result = refreshButtonState(null, { configured: false, state: "" });
    assert.equal(result.label, "Unavailable");
    assert.equal(result.disabled, true);
  });

  it("distinguishes its own action from another button's", () => {
    assert.equal(refreshButtonState("alt-refresh", ready, "alt-refresh").label, "Refreshing…");
    assert.equal(refreshButtonState("alt-refresh", ready, "refresh").label, "Working…");
  });
});

describe("connectionState", () => {
  it("reports readiness plainly", () => {
    const result = connectionState({ state: "latest reading complete", error: null });
    assert.equal(result.text, "Local BLE ready");
    assert.equal(result.modifier, "connected");
  });
  it("surfaces the collector's own words otherwise", () => {
    assert.equal(connectionState({ state: "scanning", error: null }).text, "scanning");
  });
  it("marks an error", () => {
    assert.equal(connectionState({ state: "not found", error: "boom" }).modifier, "error");
  });
});

describe("freshness", () => {
  const now = Date.UTC(2026, 0, 1, 12, 0, 0);
  const reading = (minutesAgo) => ({
    timestamp: new Date(now - minutesAgo * 60000).toISOString(),
  });

  it("shows the time plainly when the reading is current", () => {
    const result = freshness(
      { latest: reading(1), error: null }, now);
    assert.equal(result.stale, false);
    assert.match(result.text, /Updated/);
  });

  it("says how old the numbers are when the device is unreachable", () => {
    // The real case: a device powers itself off and the dashboard keeps showing
    // its last snapshot as though it were current.
    const result = freshness(
      { latest: reading(198), error: "No DELTA 2 was found." }, now);
    assert.equal(result.stale, true);
    assert.match(result.text, /Not reachable/);
    assert.match(result.text, /3 hours ago/);
    assert.match(result.text, /No DELTA 2 was found/);
  });

  it("marks readings stale once they stop arriving, even without an error", () => {
    const result = freshness({ latest: reading(45), error: null }, now);
    assert.equal(result.stale, true);
    assert.match(result.text, /45 minutes ago/);
  });

  it("explains itself when there is nothing to show at all", () => {
    const result = freshness({ latest: null, error: "No DC to DC was found." }, now);
    assert.equal(result.stale, true);
    assert.match(result.text, /No DC to DC was found/);
  });
});

describe("ageInWords", () => {
  const minutes = (n) => n * 60000;
  it("reads naturally at each scale", () => {
    assert.equal(ageInWords(minutes(0.5)), "just now");
    assert.equal(ageInWords(minutes(1)), "1 minute ago");
    assert.equal(ageInWords(minutes(45)), "45 minutes ago");
    assert.equal(ageInWords(minutes(60)), "1 hour ago");
    assert.equal(ageInWords(minutes(198)), "3 hours ago");
    assert.equal(ageInWords(minutes(60 * 72)), "3 days ago");
  });
});
