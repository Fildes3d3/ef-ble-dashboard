// The power history chart. `chartScale` is the maths and is tested; `drawChart`
// is the canvas glue around it.

import { plural } from "./format.js";

export function rangeLabel(items) {
  if (items.length < 2) return "RECENT HISTORY";
  const span = new Date(items[items.length - 1].timestamp) - new Date(items[0].timestamp);
  const minutes = Math.round(span / 60000);
  if (minutes < 1) return "LAST FEW SECONDS";
  if (minutes < 90) return `LAST ${plural(minutes, "MINUTE")}`;
  return `LAST ${plural(Math.round(minutes / 60), "HOUR")}`;
}


const SERIES_COLOURS = ["#d7ff6a", "#f6f9ef"];

/**
 * Work out the vertical range for a series.
 *
 * dc_power is bidirectional: negative means the charger is pushing power back out
 * to the vehicle battery. Scaling from zero upwards would put those points off the
 * bottom of the canvas entirely. A missing reading is not a zero and is excluded.
 */
export function chartScale(items, keys) {
  const values = items.flatMap(item => keys.map(key => item[key])).filter(v => v != null);
  if (!values.length) return { empty: true };
  const peak = Math.max(...values.map(Math.abs));
  const high = Math.max(20, ...values);
  const low = Math.min(0, ...values);
  return { empty: false, peak, high, low, span: high - low, flat: peak === 0 };
}

function label(context, text, width, height) {
  context.fillStyle = "#7f9280";
  context.font = "13px Inter, system-ui, sans-serif";
  context.textAlign = "center";
  context.fillText(text, width / 2, height / 2);
}

export function drawChart(
  items,
  canvasId = "power-chart",
  rangeId = "chart-range",
  keys = ["input_power", "output_power"],
) {
  document.querySelector(`#${rangeId}`).textContent = rangeLabel(items);
  const canvas = document.querySelector(`#${canvasId}`);
  const context = canvas.getContext("2d");
  canvas.width = canvas.clientWidth * devicePixelRatio;
  canvas.height = canvas.clientHeight * devicePixelRatio;
  context.scale(devicePixelRatio, devicePixelRatio);
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  context.clearRect(0, 0, width, height);

  context.strokeStyle = "#ffffff12";
  context.lineWidth = 1;
  for (let index = 1; index < 4; index += 1) {
    const y = height * index / 4;
    context.beginPath(); context.moveTo(0, y); context.lineTo(width, y); context.stroke();
  }

  if (!items.length) return label(context, "No readings yet", width, height);
  const scale = chartScale(items, keys);
  if (scale.empty) return label(context, "No readings in this period", width, height);
  if (scale.flat) label(context, "Flat at 0 W for this whole period", width, height);

  const y = (reading) => height - ((reading - scale.low) / scale.span * (height - 10)) - 5;

  if (scale.low < 0) {
    context.strokeStyle = "#ffffff30";
    context.setLineDash([4, 4]);
    context.beginPath(); context.moveTo(0, y(0)); context.lineTo(width, y(0)); context.stroke();
    context.setLineDash([]);
  }

  keys.forEach((key, index) => {
    if (!items.length) return;
    context.strokeStyle = SERIES_COLOURS[index % SERIES_COLOURS.length];
    context.lineWidth = 2;
    context.lineJoin = "round";
    context.beginPath();
    let drawing = false;
    items.forEach((item, position) => {
      const reading = item[key];
      if (reading == null) { drawing = false; return; }  // break the line, don't invent a zero
      const x = items.length === 1 ? 0 : position * width / (items.length - 1);
      if (drawing) context.lineTo(x, y(reading));
      else { context.moveTo(x, y(reading)); drawing = true; }
    });
    context.stroke();
  });
}
