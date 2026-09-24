// Shared mutable state. Small, and deliberately in one place rather than spread
// across modules as free variables.

export const BUSY_STATES = new Set(["scanning", "authenticating", "collecting"]);

export const state = {
  // null, "refresh", "alt-refresh", or a control key while a command is in flight.
  pendingAction: null,
  lastStatus: { configured: true, state: "" },
  lastSnapshot: null,
  activeDevice: "delta2",
};

/** True when the radio is busy, either with our command or the collector's own poll. */
export const isBusy = () =>
  state.pendingAction !== null || BUSY_STATES.has(state.lastStatus.state);
