// Entry point: wiring, polling and the handlers. Everything it calls lives in the
// modules beside it.

import {
  getHealth, getHistory, getSession, getStatus,
  requestRefresh, signIn, signOut, writeControl,
} from "./api.js";
import { drawChart } from "./chart.js";
import { state } from "./store.js";
import {
  connectionPill, render, renderAlternator, renderDetail, setText, showFreshness,
  updateRefreshButton,
} from "./views.js";

const loginView = document.querySelector("#login-view");
const dashboardView = document.querySelector("#dashboard-view");

// The dashboard is left open for hours while the code behind it changes. Without
// this, a tab keeps running whatever JavaScript it loaded - including a version
// with a function that no longer exists - and only a manual reload fixes it.
const PAGE_VERSION = new URL(
  document.querySelector('script[src*="main.js"]').src
).searchParams.get("v");

async function reloadIfStale() {
  try {
    const health = await getHealth();
    if (PAGE_VERSION && health.version && health.version !== PAGE_VERSION) {
      location.reload();
    }
  } catch { /* offline or restarting; try again on the next tick */ }
}

/** Run a Bluetooth action, keeping the UI honest about what is happening. */
async function perform(action, note, run) {
  if (state.pendingAction) return;
  state.pendingAction = action;
  updateRefreshButton();
  renderDetail(state.lastSnapshot);
  setText("status-note", note);
  try {
    const result = await run();
    state.pendingAction = null;
    await updateDashboard();
    return result;
  } catch (error) {
    state.pendingAction = null;
    setText("status-note", error.message);
  } finally {
    state.pendingAction = null;
    updateRefreshButton();
  }
}

// groups.js builds the widgets but must not import the network layer, so the
// handler is handed to it here.
state.onControl = (key, label, value, describe) =>
  perform(key, `${describe} over Bluetooth — this takes about half a minute.`, async () => {
    const result = await writeControl(key, value);
    if (!result.confirmed) {
      setText("status-note", `${label} did not confirm the change. The unit may have refused it.`);
    }
    return result;
  });

export async function updateDashboard() {
  try {
    const [status, history] = await Promise.all([
      getStatus(),
      getHistory(state.activeDevice),
    ]);
    const device = status.devices[state.activeDevice];
    if (state.activeDevice === "alternator") {
      renderAlternator(device.latest, device);
      drawChart(history.items, "alt-power-chart", "alt-chart-range", ["dc_power"]);
      connectionPill(device);
      if (!state.pendingAction) showFreshness(device);
    } else {
      render(device.latest, device);
      drawChart(history.items);
    }
  } catch (error) {
    if (error.message === "Sign in required.") showLogin();
    else setText("status-note", error.message);
  }
}

function showLogin() {
  dashboardView.hidden = true;
  loginView.hidden = false;
}

function showDashboard() {
  loginView.hidden = true;
  dashboardView.hidden = false;
  updateDashboard();
}

document.querySelector("#login-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await signIn(document.querySelector("#password").value);
    showDashboard();
  } catch (error) {
    setText("login-error", error.message);
  }
});

document.querySelector("#logout-button").addEventListener("click", async () => {
  await signOut();
  showLogin();
});

document.querySelector("#refresh-button").addEventListener("click", () =>
  perform("refresh", "Reading the DELTA 2 over Bluetooth — this can take up to a minute.",
    () => requestRefresh("delta2")));

document.querySelector("#alt-refresh-button").addEventListener("click", () =>
  perform("alt-refresh", "Reading the alternator charger over Bluetooth…",
    () => requestRefresh("alternator")));

document.querySelectorAll("#tabs .tab").forEach(tab => {
  tab.addEventListener("click", () => {
    state.activeDevice = tab.dataset.device;
    for (const other of document.querySelectorAll("#tabs .tab")) {
      const active = other === tab;
      other.classList.toggle("is-active", active);
      if (active) other.setAttribute("aria-current", "page");
      else other.removeAttribute("aria-current");
    }
    document.querySelector("#panel-delta2").hidden = state.activeDevice !== "delta2";
    document.querySelector("#panel-alternator").hidden = state.activeDevice !== "alternator";
    updateDashboard();
  });
});

getSession().then(data => (data.authenticated ? showDashboard() : showLogin()));
setInterval(() => { if (!dashboardView.hidden) updateDashboard(); }, 10000);
setInterval(reloadIfStale, 15000);
reloadIfStale();
