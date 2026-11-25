import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowRight,
  ArrowUpDown,
  ChevronDown,
  ChevronUp,
  Moon,
  Pencil,
  Sun,
  Globe2,
  History,
  Info,
  Navigation,
  Plane,
  RotateCcw,
  SlidersHorizontal,
} from "lucide-react";
import AirportField from "./AirportField";
import Guide from "./Guide";
import { keepRoute } from "./flightDraft";
import Timeline from "./Timeline";
import WeatherLayers from "./WeatherLayers";
import { nearby, type LayerChoice } from "./observations";
import { useObservations } from "./useObservations";
import { applyTheme, categoryColor, type Theme } from "./theme";
import {
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
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "light" ? "light" : "dark",
  );
  const [editing, setEditing] = useState(false);
  const editButton = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => applyTheme(theme), [theme]);
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
  const [layerChoice, setLayerChoice] = useState<LayerChoice>({
    sigmet: false,
    report: false,
  });
  const layerSource =
    forecast?.mode === "live" ? "latest" : (forecast?.run.runId ?? "");
  const weather = useObservations(
    layerSource,
    Boolean(
      forecast &&
      source === layerSource &&
      (layerChoice.sigmet || layerChoice.report),
    ),
  );
  const visibleWeather = useMemo(
    () => weather.data?.items.filter((item) => layerChoice[item.kind]) ?? [],
    [weather.data, layerChoice],
  );
  const nearbyWeather =
    forecast && weather.data
      ? nearby(visibleWeather, forecast.samples[point])
      : null;
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
          return true;
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
      return false;
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
  const formExpanded = editing || !forecast;
  const themeAction =
    theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  return (
    <>
      <header className="topbar">
        <div className="nav-inner">
          <a href="/" className="brand" aria-label="SkyCalm home">
            <svg className="brand-mark" viewBox="0 0 48 48" aria-hidden="true">
              <use href="/skycalm.svg#plane" />
            </svg>
            <span>SkyCalm</span>
          </a>
          <div className="nav-actions">
            <a
              href="/history"
              className="guide-button passenger-link"
              aria-label="Route history"
              title="Route history"
            >
              <History size={16} />
              <span>Route history</span>
            </a>
            <a
              href="/flights"
              className="guide-button passenger-link"
              aria-label="My flights"
            >
              <Plane size={16} />
              <span>My flights</span>
            </a>
            <Guide />
            <button
              className="theme-toggle"
              type="button"
              aria-label={themeAction}
              title={themeAction}
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              {theme === "dark" ? <Sun size={19} /> : <Moon size={19} />}
            </button>
          </div>
        </div>
      </header>
      <main id="forecast" className="shell">
        <div className="page-title">
          <div>
            <h1>Flight forecast</h1>
            <p>European routes · 36-hour forecast window</p>
          </div>
          {catalog && (
            <div className="source-control" data-replay={source !== "latest"}>
              <span className="source-icon">
                {source === "latest" ? (
                  <Globe2 size={18} />
                ) : (
                  <RotateCcw size={18} />
                )}
              </span>
              <div className="source-content">
                <label htmlFor="source">Weather source</label>
                <div className="source-select">
                  <select
                    id="source"
                    value={source}
                    onChange={(e) => switchSource(e.target.value)}
                  >
                    {catalog.latest && (
                      <option value="latest">
                        Latest · {fmt(catalog.latest)}
                      </option>
                    )}
                    {catalog.replays.map((r) => (
                      <option key={r.runId} value={r.runId}>
                        Replay · {fmt(r)}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={15} aria-hidden="true" />
                </div>
              </div>
            </div>
          )}
        </div>
        <div className="workspace">
          <section
            className="planner card"
            data-expanded={formExpanded}
            aria-label="Your flight"
          >
            <div className="planner-heading">
              <div className="card-title">
                <span className="section-icon">
                  <SlidersHorizontal size={17} />
                </span>
                <h2>Your flight</h2>
              </div>
              {forecast && !formExpanded && (
                <p className="flight-summary">
                  <strong>
                    {forecast.origin.code} <ArrowRight size={13} />{" "}
                    {forecast.destination.code}
                  </strong>
                  <span>
                    {dateLabel(forecast.departure)} ·{" "}
                    {clock(forecast.departure)} UTC
                  </span>
                </p>
              )}
              {forecast && (
                <button
                  type="button"
                  className="edit-flight"
                  ref={editButton}
                  aria-controls="flight-form"
                  aria-expanded={formExpanded}
                  onClick={() => setEditing(!editing)}
                >
                  {editing ? <ChevronUp size={15} /> : <Pencil size={14} />}
                  {editing ? "Close" : "Edit flight"}
                </button>
              )}
            </div>
            <form
              id="flight-form"
              onSubmit={async (e) => {
                e.preventDefault();
                if (
                  origin &&
                  dest &&
                  departure &&
                  source &&
                  (await load(origin, dest, departure, source))
                ) {
                  setEditing(false);
                  if (editButton.current?.offsetWidth)
                    editButton.current.focus({ preventScroll: true });
                }
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
              </button>
              {dirty && !loading && (
                <p className="dirty">
                  Update the forecast to see your changes.
                </p>
              )}
            </form>
            <div className="data-note" data-replay={source !== "latest"}>
              <Globe2 size={16} />
              <div>
                <b>{meta?.source || "NOAA GFS"}</b>
                <span>
                  {meta ? fmt(meta) : "European weather grid"}
                  {source && source !== "latest" ? " · Replay" : ""}
                </span>
              </div>
              {forecast && (
                <a
                  className="save-route-link"
                  href="/flights"
                  onClick={() => keepRoute(forecast)}
                >
                  Save route
                </a>
              )}
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
                <div className="map-viewport">
                  <WeatherLayers
                    choice={layerChoice}
                    onChange={setLayerChoice}
                    data={weather.data}
                    loading={weather.loading}
                    error={weather.error}
                    onRetry={weather.retry}
                  />
                  <Suspense
                    fallback={<div className="map-wait">Loading the map…</div>}
                  >
                    <RouteGlobe
                      theme={theme}
                      samples={forecast.samples}
                      origin={forecast.origin}
                      destination={forecast.destination}
                      selected={point}
                      onSelect={setPoint}
                      observations={visibleWeather}
                    />
                  </Suspense>
                </div>
                <div className="legend" aria-label="Intensity legend">
                  {classes.map((c) => (
                    <span key={c}>
                      <i style={{ background: categoryColor(c) }} />
                      {LABELS[c]}
                    </span>
                  ))}
                  {forecast.samples.some(
                    (s) => s.category === "unavailable",
                  ) && (
                    <span>
                      <i style={{ background: categoryColor("unavailable") }} />
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
          <Timeline
            forecast={forecast}
            index={point}
            onSelect={setPoint}
            observations={nearbyWeather}
          />
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
