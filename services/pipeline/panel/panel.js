const el = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="skycalm-token"]').content;
const healthPage = location.pathname === "/health";
let cloud = false;
let pollTimer;
let polling = false;
let current = JSON.parse(sessionStorage.getItem("skycalm-run") || "null");
function setCurrent(value) {
  current = value;
  if (value) sessionStorage.setItem("skycalm-run", JSON.stringify(value));
  else sessionStorage.removeItem("skycalm-run");
}
function notice(text = "") {
  el("error").textContent = text;
  el("error").hidden = !text;
}
function node(tag, text) {
  const n = document.createElement(tag);
  n.textContent = text;
  return n;
}
function dateLabel(run) {
  const part = run.split("-");
  return (
    part[1].slice(0, 4) +
    "-" +
    part[1].slice(4, 6) +
    "-" +
    part[1].slice(6, 8) +
    " · " +
    part[2] +
    ":00 UTC"
  );
}
async function api(path, body) {
  const headers = { "X-SkyCalm-Token": token };
  if (body) headers["Content-Type"] = "application/json";
  const response = await fetch("/api/" + path, {
    method: body ? "POST" : "GET",
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(path === "discover" ? 115000 : 40000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}
function displayRoute(route) {
  const ribbon = el("ribbon");
  ribbon.replaceChildren();
  el("legend").hidden = !route;
  el("peak").textContent = route ? "Peak · " + route.peak : "";
  el("route-status").textContent = route
    ? route.departure.replace("T", " ").replace("Z", " UTC") +
      " · " +
      route.durationMinutes +
      " min · " +
      route.categories.length +
      " sample points"
    : "The updated forecast appears here when the run finishes.";
  ribbon.setAttribute(
    "aria-label",
    route
      ? "Forecast along the route. Peak " + route.peak
      : "No updated forecast",
  );
  for (const category of route?.categories || []) {
    const span = node("i", "");
    span.className = category;
    span.title = category;
    ribbon.append(span);
  }
}
function busy(yes) {
  el("publish").disabled = yes;
  el("discover").disabled = yes;
  el("run").disabled = yes;
}
function showStatus(job) {
  const phases = ["queued", "building", "delivering", "ready"];
  const at = phases.indexOf(job.phase);
  [...el("steps").children].forEach((step, i) => {
    step.classList.toggle("done", i < at || at === 3);
    if (i === at && at !== 3) step.setAttribute("aria-current", "step");
    else step.removeAttribute("aria-current");
  });
  const seconds = Math.max(
    0,
    Math.round(((current.ended || Date.now()) - current.started) / 1000),
  );
  el("clock").textContent = seconds + " s";
  el("job-id").textContent = current.id;
  const words = {
    queued: "Waiting for the grid worker.",
    building: "Computing forecast tiles.",
    delivering: cloud
      ? "Updating the route and recording delivery."
      : "Updating the route.",
    ready: "Route updated.",
    failed: "Run failed. " + (job.reason || "See operator health."),
    unknown: "Waiting for admission.",
  };
  el("job-status").textContent = words[job.phase] || "Waiting for progress.";
  displayRoute(job.route);
}
async function poll() {
  if (polling || !current) return;
  polling = true;
  try {
    const job = await api("jobs/" + current.id);
    if (!cloud && job.phase === "unknown") {
      setCurrent(null);
      busy(false);
      el("job-status").textContent = "Start a new local rehearsal.";
      return;
    }
    if (["ready", "failed"].includes(job.phase)) {
      if (!current.ended) setCurrent({ ...current, ended: Date.now() });
      busy(false);
    } else if (Date.now() - current.started > 930000) {
      busy(false);
      notice(
        "The progress window has ended. Check service health before publishing again.",
      );
      return;
    } else {
      busy(true);
      pollTimer = setTimeout(poll, cloud ? 2500 : 450);
    }
    showStatus(job);
  } catch (error) {
    notice(error.message);
    if (Date.now() - current.started < 930000)
      pollTimer = setTimeout(poll, 5000);
    else busy(false);
  } finally {
    polling = false;
  }
}
const requestId = () => crypto.randomUUID().replaceAll("-", "");
let pending = null;
async function publish() {
  notice();
  busy(true);
  clearTimeout(pollTimer);
  const run = el("run").value;
  if (!pending || pending.run !== run)
    pending = { requestId: requestId(), run, started: Date.now() };
  try {
    const job = await api("publish", { requestId: pending.requestId, run });
    setCurrent({
      id: job.jobId,
      started: pending.started,
      mode: cloud ? "aws" : "local",
    });
    pending = null;
    await poll();
  } catch (error) {
    notice(error.message);
    busy(false);
  }
}
async function discover() {
  notice();
  busy(true);
  const started = Date.now();
  try {
    const result = await api("discover", { requestId: requestId() });
    if (result.found) {
      setCurrent({ id: result.jobId, started, mode: "aws" });
      await poll();
    } else {
      el("job-status").textContent =
        "The serving grid is up to date or the next NOAA run is incomplete.";
      busy(false);
    }
  } catch (error) {
    notice(error.message);
    busy(false);
  }
}
function pair(list, label, value) {
  list.append(node("dt", label), node("dd", value || "Unavailable"));
}
async function health() {
  notice();
  el("refresh").disabled = true;
  try {
    const data = await api("health");
    const list = el("services");
    list.replaceChildren();
    pair(list, "Active grid worker", data.active || "Idle");
    if (cloud) {
      pair(list, "Latest forecast", data.latestRun);
      pair(list, "Weather observations", data.observations);
    }
    pair(list, "Aircraft positions", "Awaiting OpenSky permission");
    pair(list, "Forecast model", "Ellrod TI1 / surface CAPE");
    pair(list, "Passenger notifications", "Planned for Phase 4");
    el("cloud-health").hidden = !cloud;
    el("test-controls").hidden = !cloud;
    el("queues").replaceChildren();
    el("alarms").replaceChildren();
    for (const [name, q] of Object.entries(data.queues)) {
      const tr = node("tr", "");
      tr.append(
        node("td", name),
        node("td", q.visible),
        node("td", q.processing),
      );
      el("queues").append(tr);
    }
    for (const [name, state] of Object.entries(data.alarms))
      pair(el("alarms"), name, state);
  } catch (error) {
    notice(error.message);
  } finally {
    el("refresh").disabled = false;
  }
}
el("publish").addEventListener("click", publish);
el("discover").addEventListener("click", discover);
el("refresh").addEventListener("click", health);
el("probe").addEventListener("click", async () => {
  el("probe").disabled = true;
  notice();
  try {
    const r = await api("probe", { requestId: requestId() });
    el("probe-status").textContent =
      "Test submitted · " +
      r.testId +
      ". Refresh health to see redrive and the alarm.";
  } catch (error) {
    notice(error.message);
  } finally {
    el("probe").disabled = false;
  }
});
try {
  const session = await api("session");
  cloud = session.cloud;
  el("environment").textContent = session.mode;
  el(healthPage ? "health-link" : "demo-link").setAttribute(
    "aria-current",
    "page",
  );
  el(healthPage ? "health" : "demo").hidden = false;
  el("cloud-actions").hidden = !cloud;
  for (const run of session.runs) {
    const option = node("option", dateLabel(run));
    option.value = run;
    el("run").append(option);
  }
  if (healthPage) await health();
  else if (current && current.mode === (cloud ? "aws" : "local")) await poll();
  else {
    setCurrent(null);
    busy(false);
  }
} catch (error) {
  notice(error.message);
}
