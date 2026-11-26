import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { LevelButton } from "./CabinGuide";
import { clock, dateLabel, fetchWithRetry, type Category } from "./types";
import "./history.css";

interface Report {
  source: string;
  observed: string;
  altitude_ft: number;
  distance_km: number;
  elapsed_minutes: number;
  reported: Category;
  forecast: Category;
}
interface ArchiveDay {
  origin: string;
  destination: string;
  run_id: string;
  departure: string;
  peak: Category;
  snapshot_at: string;
  reports: Report[];
}
const routes = [
  { code: "EDI-OPO", label: "Edinburgh → Porto" },
  { code: "AMS-LHR", label: "Amsterdam → London Heathrow" },
  { code: "BCN-ARN", label: "Barcelona → Stockholm Arlanda" },
];
const categories = [
  "smooth",
  "light",
  "moderate",
  "severe",
  "unavailable",
] as const;

export default function RouteHistory() {
  const [rows, setRows] = useState<ArchiveDay[]>([]);
  const [route, setRoute] = useState(routes[0].code);
  const [selected, setSelected] = useState("gfs-20261121-06");
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetchWithRetry("/data/route-history/days.jsonl", 8000, controller.signal)
      .then(async (res) => {
        if (!res.ok) throw new Error("Archive unavailable");
        const days = (await res.text())
          .trim()
          .split("\n")
          .map((line) => JSON.parse(line) as ArchiveDay);
        if (!controller.signal.aborted) setRows(days);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, []);
  const dates = rows.filter((d) => d.origin + "-" + d.destination === route);
  const day = dates.find((d) => d.run_id === selected) ?? dates[0];
  return (
    <>
      <header className="topbar">
        <div className="nav-inner">
          <a href="/" className="brand">
            <img src="/skycalm.svg" width="32" height="32" alt="" />
            SkyCalm
          </a>
          <a className="guide-button" href="/">
            <ArrowLeft size={16} /> Flight forecast
          </a>
        </div>
      </header>
      <main className="history-shell">
        <h1>Route history</h1>
        <p className="history-intro">
          Explore five archived November 2026 forecasts and the aircraft reports
          recorded nearby.
        </p>
        <label className="history-field">
          Route
          <select value={route} onChange={(e) => setRoute(e.target.value)}>
            {routes.map((r) => (
              <option key={r.code} value={r.code}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        {error ? (
          <p role="alert">
            The route archive could not be loaded. Reload to try again.
          </p>
        ) : !day ? (
          <p role="status">Loading the route archive…</p>
        ) : (
          <div className="history-grid">
            <section className="history-card" aria-labelledby="history-peaks">
              <h2 id="history-peaks">Peak forecast by day</h2>
              <p>
                {dates.length} departures · {dateLabel(dates[0].departure)} to{" "}
                {dateLabel(dates[dates.length - 1].departure)}
              </p>
              <ul className="history-bars">
                {categories.map((c) => {
                  const n = dates.filter((d) => d.peak === c).length;
                  if (c === "unavailable" && !n) return null;
                  return (
                    <li key={c}>
                      <LevelButton level={c} />
                      <span className="history-track" aria-hidden="true">
                        <i
                          style={{
                            width: (100 * n) / dates.length + "%",
                            backgroundColor:
                              "var(--turb-" +
                              (c === "unavailable" ? "none" : c) +
                              ")",
                          }}
                        />
                      </span>
                      <strong>
                        {n}
                        <span className="sr-only"> days</span>
                      </strong>
                    </li>
                  );
                })}
              </ul>
              <p className="history-note">
                Five selected days describe this archive. A seasonal estimate
                needs a longer record.
              </p>
            </section>
            <section className="history-card" aria-labelledby="history-recap">
              <h2 id="history-recap">Post-flight recap</h2>
              <label className="history-field">
                Archived departure
                <select
                  value={day.run_id}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  {dates.map((d) => (
                    <option key={d.run_id} value={d.run_id}>
                      {dateLabel(d.departure)} · {clock(d.departure)} UTC
                    </option>
                  ))}
                </select>
              </label>
              <p>
                Peak forecast <LevelButton level={day.peak} /> ·{" "}
                {day.reports.length} matching aircraft{" "}
                {day.reports.length === 1 ? "report" : "reports"}
              </p>
              {day.reports.length ? (
                <ul className="recap-list">
                  {day.reports.map((r, i) => (
                    <li key={i}>
                      <b>
                        {r.source} · {clock(r.observed)} UTC
                      </b>
                      <span>
                        <LevelButton level={r.reported} /> reported ·{" "}
                        <LevelButton level={r.forecast} /> forecast at the
                        nearest sample
                      </span>
                      <small>
                        {r.elapsed_minutes} min along the route ·{" "}
                        {r.distance_km} km from the sample ·{" "}
                        {r.altitude_ft.toLocaleString("en-GB")} ft
                      </small>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="history-note">
                  No qualifying aircraft report was available to check this
                  flight’s forecast.
                </p>
              )}
              <details>
                <summary>How reports are matched</summary>
                <p>
                  SkyCalm pairs each aircraft report with the nearest sample
                  within 75 km, 45 minutes and 3,000 ft. Each report counts
                  once. The original forecasts used the physics baseline. The
                  observation snapshot was recorded on{" "}
                  {dateLabel(day.snapshot_at)} at {clock(day.snapshot_at)} UTC.
                </p>
              </details>
            </section>
          </div>
        )}
      </main>
    </>
  );
}
