import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  ArrowRight,
  ArrowUpDown,
  CalendarDays,
  Clock3,
  Globe2,
  Info,
  Navigation,
  Plane,
  RotateCcw,
  SlidersHorizontal,
} from "lucide-react";
import AirportField from "./AirportField";
import Guide from "./Guide";
import Timeline from "./Timeline";
import {
  COLORS,
  LABELS,
  city,
  clock,
  dateLabel,
  defaultDeparture,
  duration,
  getJson,
} from "./types";
import type { Airport, Catalog, Category, Forecast, Run } from "./types";

const RouteGlobe = lazy(() => import("./RouteGlobe"));
const classes: Category[] = ["smooth", "light", "moderate", "severe"];
const fmt = (d: Run) => dateLabel(d.issued) + " · " + clock(d.issued) + " UTC";

export default function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [source, setSource] = useState("");
  const [origin, setOrigin] = useState<Airport | null>(null);
  const [dest, setDest] = useState<Airport | null>(null);
  const [departure, setDeparture] = useState("");
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [point, setPoint] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const flightRequest = useRef<AbortController | null>(null);

  const load = useCallback(
    async (from: Airport, to: Airport, when: string, run: string) => {
      flightRequest.current?.abort();
      const ctrl = new AbortController();
      flightRequest.current = ctrl;
      setLoading(true);
      setError("");
      try {
        const f = await getJson<Forecast>(
          "/api/forecast",
          {
            origin: from.code,
            destination: to.code,
            departure: when + ":00Z",
            run,
          },
          ctrl.signal,
        );
        if (!ctrl.signal.aborted) {
          setForecast(f);
          setPoint(Math.floor((f.samples.length - 1) / 2));
        }
      } catch (e) {
        if (!ctrl.signal.aborted) {
          setForecast(null);
          setError(
            e instanceof Error
              ? e.message
              : "The forecast could not be loaded.",
          );
        }
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    },
    [],
  );
  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      getJson<Catalog>("/api/runs", {}, ctrl.signal),
      getJson<{ airports: Airport[] }>("/api/airports", {}, ctrl.signal),
    ])
      .then(([c, available]) => {
        if (ctrl.signal.aborted) return;
        const from = available.airports.find((a) => a.code === "BCN"),
          to = available.airports.find((a) => a.code === "ARN");
        if (!from || !to)
          throw new Error("The airport directory is unavailable.");
        setOrigin(from);
        setDest(to);
        setCatalog(c);
        const live =
          !!c.latest &&
          Date.parse(c.latest.validUntil) > Date.parse(c.serverTime) + 5400000;
        const run = live ? c.latest : c.replays[0];
        if (!run) throw new Error("No weather run is available yet.");
        const choice = live ? "latest" : run.runId;
        const when = defaultDeparture(run, live, c.serverTime);
        setSource(choice);
        setDeparture(when);
        return load(from, to, when, choice);
      })
      .catch((e) => {
        if (!ctrl.signal.aborted) {
          setError(e instanceof Error ? e.message : "The app could not load.");
          setLoading(false);
        }
      });
    return () => {
      ctrl.abort();
      flightRequest.current?.abort();
    };
  }, [attempt, load]);
  function switchSource(selection: string) {
    if (!catalog) return;
    const run =
      selection === "latest"
        ? catalog.latest
        : catalog.replays.find((r) => r.runId === selection);
    if (!run) return;
    const when = defaultDeparture(
      run,
      selection === "latest",
      catalog.serverTime,
    );
    setSource(selection);
    setDeparture(when);
    if (origin && dest) void load(origin, dest, when, selection);
  }
  const dirty =
    forecast &&
    (forecast.origin.code !== origin?.code ||
      forecast.destination.code !== dest?.code ||
      forecast.departure.slice(0, 16) !== departure);
  const meta =
    source === "latest"
      ? catalog?.latest
      : catalog?.replays.find((r) => r.runId === source);
  return (
    <>
      <header className="topbar">
        <div className="nav-inner">
          <a href="/" className="brand" aria-label="SkyCalm home">
            <img src="/skycalm.svg" alt="" />
            <span>SkyCalm</span>
          </a>
          <a className="nav-current" href="#forecast">
            <span />
            Flight forecast
          </a>
          <Guide />
        </div>
      </header>
      <main id="forecast" className="shell">
        <div className="page-title">
          <div>
            <h1>Flight forecast</h1>
            <p>Explore the air along your European flight.</p>
          </div>
          {catalog && (
            <div className="source-control">
              <span className="source-icon">
                {source === "latest" ? (
                  <Globe2 size={18} />
                ) : (
                  <RotateCcw size={18} />
                )}
              </span>
              <div>
                <label htmlFor="source">Weather source</label>
                <select
                  id="source"
                  value={source}
                  onChange={(e) => switchSource(e.target.value)}
                >
                  {catalog.latest && (
                    <option value="latest">Latest forecast</option>
                  )}
                  {catalog.replays.map((r) => (
                    <option key={r.runId} value={r.runId}>
                      Replay · {fmt(r)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>
        <div className="workspace">
          <section className="planner card">
            <div className="card-title">
              <span className="section-icon">
                <SlidersHorizontal size={17} />
              </span>
              <h2>Your flight</h2>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (origin && dest && departure && source)
                  void load(origin, dest, departure, source);
              }}
            >
              <div className="airport-pair">
                <AirportField
                  label="Departure airport"
                  selected={origin}
                  onChange={setOrigin}
                />
                <button
                  className="swap"
                  type="button"
                  aria-label="Swap airports"
                  onClick={() => {
                    setOrigin(dest);
                    setDest(origin);
                  }}
                >
                  <ArrowUpDown size={14} />
                </button>
                <AirportField
                  label="Arrival airport"
                  selected={dest}
                  onChange={setDest}
                />
              </div>
              <div className="date-grid">
                <label>
                  Departure date
                  <span className="native-field">
                    <CalendarDays size={15} />
                    <input
                      required
                      type="date"
                      aria-label="Departure date"
                      value={departure.slice(0, 10)}
                      onChange={(e) =>
                        setDeparture(
                          e.target.value +
                            "T" +
                            (departure.slice(11) || "00:00"),
                        )
                      }
                    />
                  </span>
                </label>
                <label>
                  Time (UTC)
                  <span className="native-field">
                    <Clock3 size={15} />
                    <input
                      required
                      type="time"
                      aria-label="Departure time UTC"
                      value={departure.slice(11)}
                      onChange={(e) =>
                        setDeparture(
                          departure.slice(0, 10) + "T" + e.target.value,
                        )
                      }
                    />
                  </span>
                </label>
              </div>
              <button
                type="submit"
                className="submit"
                disabled={loading || !origin || !dest || !source}
              >
                {loading ? "Loading forecast…" : "Forecast flight"}
                <ArrowRight size={17} />
              </button>
              {dirty && !loading && (
                <p className="dirty">
                  Update the forecast to see your changes.
                </p>
              )}
            </form>
            <div className="data-note">
              <Globe2 size={16} />
              <div>
                <b>{meta?.source || "NOAA GFS"}</b>
                <span>
                  {meta ? fmt(meta) : "European weather grid"}
                  {source && source !== "latest" ? " · Replay" : ""}
                </span>
              </div>
            </div>
          </section>
          <section className="map-card card" aria-label="Flight map">
            {forecast ? (
              <>
                <div className="map-title">
                  <div>
                    <div className="route-codes">
                      <strong>{forecast.origin.code}</strong>
                      <ArrowRight size={20} />
                      <strong>{forecast.destination.code}</strong>
                    </div>
                    <p>
                      {city(forecast.origin)} to {city(forecast.destination)}
                    </p>
                  </div>
                  <span className="route-stat">
                    <Plane size={14} />
                    {duration(forecast.durationMinutes)}
                    <i />
                    {forecast.distanceKm.toLocaleString("en-GB")} km
                  </span>
                </div>
                <Suspense
                  fallback={<div className="map-wait">Loading the map…</div>}
                >
                  <RouteGlobe
                    samples={forecast.samples}
                    origin={forecast.origin}
                    destination={forecast.destination}
                    selected={point}
                    onSelect={setPoint}
                  />
                </Suspense>
                <div className="legend" aria-label="Intensity legend">
                  {classes.map((c) => (
                    <span key={c}>
                      <i style={{ background: COLORS[c] }} />
                      {LABELS[c]}
                    </span>
                  ))}
                  {forecast.samples.some(
                    (s) => s.category === "unavailable",
                  ) && (
                    <span>
                      <i style={{ background: COLORS.unavailable }} />
                      Unavailable
                    </span>
                  )}
                </div>
              </>
            ) : (
              <div className="empty-map" role={error ? "alert" : "status"}>
                <span className="empty-icon">
                  <Navigation size={26} />
                </span>
                <h2>
                  {error ? "Forecast unavailable" : "Loading your route…"}
                </h2>
                {error && <p>{error}</p>}
                {error && !catalog && (
                  <button onClick={() => setAttempt((a) => a + 1)}>
                    Try again
                  </button>
                )}
              </div>
            )}
          </section>
        </div>
        {forecast && (
          <Timeline forecast={forecast} index={point} onSelect={setPoint} />
        )}
        <footer className="foot">
          <Info size={14} />
          <p>
            For passenger education only. Do not use for navigation, flight
            planning or safety decisions.
          </p>
        </footer>
      </main>
    </>
  );
}
