import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { chargerMode, fmt, number, plural, time } from "../../static/js/format.js";

describe("number", () => {
  it("rounds and appends a suffix", () => {
    assert.equal(number(52.94, " V"), "53 V");
  });
  it("shows a dash for a value the device did not report", () => {
    assert.equal(number(null), "—");
    assert.equal(number(undefined), "—");
  });
  it("does not turn zero into a dash", () => {
    assert.equal(number(0, " W"), "0 W");
  });
});

describe("time", () => {
  it("splits minutes into hours and minutes", () => {
    assert.equal(time(150), "2h 30m");
  });
  it("omits the hours below an hour", () => {
    assert.equal(time(45), "45m");
  });
  it("treats zero and negatives as unknown", () => {
    assert.equal(time(0), "—");
    assert.equal(time(-5), "—");
    assert.equal(time(null), "—");
  });
});

describe("fmt", () => {
  it("keeps two decimals for volts and amps", () => {
    assert.equal(fmt.v(13.9), "13.90 V");
    assert.equal(fmt.a(0), "0.00 A");
  });
  it("distinguishes live state from permitted state", () => {
    assert.equal(fmt.onOff(1), "On");
    assert.equal(fmt.enabled(1), "Enabled");
    assert.equal(fmt.enabled(0), "Disabled");
  });
  it("shows a dash rather than inventing a value", () => {
    for (const format of Object.values(fmt)) {
      assert.equal(format(null), "—");
    }
  });
});

describe("chargerMode", () => {
  it("names the modes the charger reports", () => {
    assert.equal(chargerMode(0), "Idle");
    assert.equal(chargerMode(2), "Battery maintenance");
  });
  it("does not hide a mode it does not recognise", () => {
    assert.equal(chargerMode(7), "Mode 7");
  });
});

describe("plural", () => {
  it("only pluralises when it should", () => {
    assert.equal(plural(1, "MINUTE"), "1 MINUTE");
    assert.equal(plural(2, "MINUTE"), "2 MINUTES");
    assert.equal(plural(0, "MINUTE"), "0 MINUTES");
  });
});
