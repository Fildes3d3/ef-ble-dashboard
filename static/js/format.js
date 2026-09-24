// Pure formatting. No DOM, no network - everything here is unit tested.

export const number = (value, suffix = "") => value == null ? "—" : `${Math.round(value)}${suffix}`;
export const time = (minutes) => {
  if (minutes == null || minutes <= 0) return "—";
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours}h ${Math.round(minutes % 60)}m` : `${Math.round(minutes)}m`;
};

export const fmt = {
  w: v => v == null ? "—" : `${Math.round(v)} W`,
  v: v => v == null ? "—" : `${v.toFixed(2)} V`,
  a: v => v == null ? "—" : `${v.toFixed(2)} A`,
  mv: v => v == null ? "—" : `${Math.round(v)} mV`,
  c: v => v == null ? "—" : `${Math.round(v)} °C`,
  pct: v => v == null ? "—" : `${Math.round(v)} %`,
  onOff: v => v == null ? "—" : (v ? "On" : "Off"),
  // For settings that say what the unit is *allowed* to do. "On" reads as "doing
  // it right now", which is wrong: ac_charging is the charge-pause flag inverted,
  // so it stays true while the unit sits at 0 W.
  enabled: v => v == null ? "—" : (v ? "Enabled" : "Disabled"),
};




export const BOOLEAN_FORMATS = new Set([fmt.onOff, fmt.enabled]);

export const CHARGER_MODES = {
  0: "Idle",
  1: "Charging while driving",
  2: "Battery maintenance",
  3: "Reverse charge",
};

export const chargerMode = v => v == null ? "—" : (CHARGER_MODES[v] ?? `Mode ${v}`);

export const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "S"}`;
