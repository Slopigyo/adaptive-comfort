(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("report-data").textContent);
  if (data.version !== 1) return;

  const byId = (id) => document.getElementById(id);
  const rows = data.routine.records;
  const unit = byId("display-unit");
  const scrubber = byId("routine-scrubber");
  const play = byId("routine-play");
  const chart = byId("routine-chart");
  const cursor = byId("routine-cursor");
  const scenario = byId("weather-select");
  const cases = Array.from(document.querySelectorAll("[data-weather-case]"));
  let selected = 0;
  let timer = null;

  const utc = (timestamp) => timestamp
    ? timestamp.replace("T", " ").replace(/(?:\+00:00|Z)$/, " UTC")
    : "Unavailable";
  const phase = (value) => value ? value.replaceAll("_", " ") : "Unavailable";
  const reasons = (values) => values.length ? values.join(", ") : "None reported";
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const temperature = (value, axis = false) => {
    if (!finite(value)) return "Unavailable";
    const displayed = unit.value === "F" ? value * 1.8 + 32 : value;
    if (!Number.isFinite(displayed)) return "Outside display range";
    const number = displayed.toFixed(axis ? 1 : 2).replace(/\.?0+$/, (match) =>
      match.startsWith(".") ? "" : match);
    return axis ? number : `${number} °${unit.value}`;
  };
  function setTemperature(id, value) {
    const node = byId(id);
    node.dataset.tempC = finite(value) ? String(value) : "";
    node.textContent = temperature(value);
  }
  function updateUnits() {
    document.querySelectorAll("[data-temp-c]").forEach((node) => {
      const raw = node.dataset.tempC;
      node.textContent = temperature(raw === "" ? null : Number(raw), node.dataset.tempMode === "axis");
    });
    document.querySelectorAll("[data-unit]").forEach((node) => {
      node.textContent = `°${unit.value}`;
    });
  }
  function showSample(index, announce = false) {
    if (!rows.length) return;
    selected = Math.max(0, Math.min(rows.length - 1, index));
    const row = rows[selected];
    scrubber.value = String(selected);
    byId("sample-position").textContent = `Sample ${selected + 1} of ${rows.length}`;
    const time = byId("sample-time");
    time.textContent = utc(row.timestamp);
    time.dateTime = row.timestamp;
    byId("sample-phase").textContent = phase(row.phase);
    byId("sample-context").textContent = row.context ?? "Unavailable";
    byId("sample-wake-date").textContent = row.wake_date ?? "Unavailable";
    byId("sample-decision").textContent = row.status;
    byId("sample-explanation").textContent = row.explanation;
    byId("sample-reasons").textContent = reasons(row.reason_codes);
    byId("sample-trace-id").textContent = row.trace_id;
    setTemperature("sample-candidate", row.candidate_c);
    setTemperature("sample-baseline", row.baseline_c);
    setTemperature("sample-indoor", row.indoor_c);
    setTemperature("sample-rounded", row.device_target_c);
    setTemperature("sample-minimum", row.allowed_minimum_c);
    setTemperature("sample-maximum", row.allowed_maximum_c);
    if (cursor) {
      const start = Number(chart.dataset.startMs);
      const end = Number(chart.dataset.endMs);
      const fraction = end > start ? (Date.parse(row.timestamp) - start) / (end - start) : 0.5;
      const x = Number(chart.dataset.left) + Math.max(0, Math.min(1, fraction)) *
        (Number(chart.dataset.right) - Number(chart.dataset.left));
      cursor.setAttribute("x1", String(x));
      cursor.setAttribute("x2", String(x));
    }
    const description = `${utc(row.timestamp)}; ${phase(row.phase)}; candidate ${temperature(row.candidate_c)}`;
    scrubber.setAttribute("aria-valuetext", description);
    if (announce) byId("sample-announcement").textContent = description;
  }
  function stop() {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
    play.textContent = "Play";
    play.setAttribute("aria-pressed", "false");
  }
  play.addEventListener("click", () => {
    if (timer !== null) {
      stop();
      return;
    }
    if (rows.length < 2) return;
    if (selected === rows.length - 1) showSample(0);
    play.textContent = "Pause";
    play.setAttribute("aria-pressed", "true");
    // Playback only selects existing samples. It never evaluates a routine or weather policy.
    timer = window.setInterval(() => {
      showSample(selected + 1);
      if (selected === rows.length - 1) {
        stop();
        byId("sample-announcement").textContent = "Playback complete. Last precomputed sample selected.";
      }
    }, 1000);
  });
  scrubber.addEventListener("input", () => {
    stop();
    showSample(Number(scrubber.value));
  });
  scrubber.addEventListener("change", () => showSample(selected, true));
  unit.addEventListener("change", () => {
    updateUnits();
    showSample(selected, true);
  });
  function showScenario() {
    cases.forEach((node) => { node.hidden = node.dataset.weatherCase !== scenario.value; });
  }
  scenario.addEventListener("change", showScenario);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });
  window.addEventListener("pagehide", stop);

  // Reveal enhancements only after their listeners and the initial sample are ready.
  // The Python-rendered charts/tables remain the fallback if initialization fails.
  unit.value = "C";
  scrubber.disabled = rows.length < 2;
  play.disabled = rows.length < 2;
  scenario.disabled = cases.length < 2;
  scenario.value = "0";
  updateUnits();
  showSample(0);
  showScenario();
  document.querySelectorAll("[data-enhanced]").forEach((node) => { node.hidden = false; });
})();
