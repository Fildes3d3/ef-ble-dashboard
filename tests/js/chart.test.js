import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { chartScale, rangeLabel } from "../../static/js/chart.js";

const at = (minutes, values) => ({
  timestamp: new Date(Date.UTC(2026, 0, 1, 0, minutes)).toISOString(),
  ...values,
});

describe("rangeLabel", () => {
  it("describes the real span of the data", () => {
    assert.equal(rangeLabel([at(0, {}), at(11, {})]), "LAST 11 MINUTES");
    assert.equal(rangeLabel([at(0, {}), at(120, {})]), "LAST 2 HOURS");
  });
  it("gets singular right", () => {
    assert.equal(rangeLabel([at(0, {}), at(1, {})]), "LAST 1 MINUTE");
  });
  it("does not claim a span it cannot know", () => {
    assert.equal(rangeLabel([]), "RECENT HISTORY");
    assert.equal(rangeLabel([at(0, {})]), "RECENT HISTORY");
  });
});

describe("chartScale", () => {
  it("reports emptiness rather than guessing a range", () => {
    assert.equal(chartScale([], ["dc_power"]).empty, true);
  });

  it("treats a series of nulls as empty, not as zeros", () => {
    const items = [at(0, { dc_power: null }), at(1, { dc_power: null })];
    assert.equal(chartScale(items, ["dc_power"]).empty, true);
  });

  it("flags a flat-zero series so the chart can say so", () => {
    const items = [at(0, { dc_power: 0 }), at(1, { dc_power: 0 })];
    assert.equal(chartScale(items, ["dc_power"]).flat, true);
  });

  it("makes room below zero for reverse charging", () => {
    // dc_power goes negative when the charger pushes power back to the vehicle.
    const items = [at(0, { dc_power: 0 }), at(1, { dc_power: -33 })];
    const scale = chartScale(items, ["dc_power"]);
    assert.equal(scale.low, -33, "the floor must reach the most negative reading");
    assert.ok(scale.span > 0);
    // Every point must land inside the drawable range.
    for (const item of items) {
      assert.ok(item.dc_power >= scale.low && item.dc_power <= scale.high);
    }
  });

  it("keeps a floor of 20 so a tiny series is not magnified into noise", () => {
    const items = [at(0, { output_power: 1 }), at(1, { output_power: 2 })];
    assert.equal(chartScale(items, ["output_power"]).high, 20);
  });

  it("ignores gaps when working out the range", () => {
    const items = [at(0, { output_power: 40 }), at(1, { output_power: null })];
    const scale = chartScale(items, ["output_power"]);
    assert.equal(scale.high, 40);
    assert.equal(scale.empty, false);
  });
});
