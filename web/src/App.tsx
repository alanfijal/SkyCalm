import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
import { keepFlight, keepRoute } from "./flightDraft";
import FlightLookup, { pendingLookup } from "./FlightLookup";
import { RecordingResults } from "./RecordingResults";
import { recordingsByRoute } from "./recordings";
import { PlaybackControls, useRoutePlayback } from "./RoutePlayback";
import { config } from "./passengerAuth";
import {
  archiveForDeparture,
  scheduleCoverage,
  type ScheduledFlight,
} from "./flightSchedule";
import { ScheduledRoutePreview } from "./ScheduledRoutePreview";
import Timeline from "./Timeline";
import { ForecastMap } from "./ForecastMap";
import { FlightSheet } from "./FlightSheet";
import { useMedia } from "./useMedia";
import { Skeleton } from "./PageSkeleton";
import { nearby, type LayerChoice } from "./observations";
import { useObservations } from "./useObservations";
import { applyTheme, type Theme } from "./theme";
import { forecastLevels, LevelButton } from "./CabinGuide";
import {
  city,
  clock,
  dateLabel,
  defaultDeparture,
  duration,
  getJson,
} from "./types";
import type { Airport, Catalog, Forecast, Run } from "./types";

const fmt = (d: Run) => dateLabel(d.issued) + " · " + clock(d.issued) + " UTC";
type RouteQuery = {
  origin: string;
  destination: string;
  departure: string;
  run: string;
  arrival?: string;
};
type RouteResult =
  | { query: RouteQuery; forecast: Forecast; byNumber: boolean }
  | { query: RouteQuery; error: string };

export default function App() {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "light" ? "light" : "dark",
  );
  const [byNumber, setByNumber] = useState(() => Boolean(pendingLookup()));
  const [lookupEnabled, setLookupEnabled] = useState(false);
  const [selectedFlight, setSelectedFlight] = useState<ScheduledFlight | null>(
    null,
  );
  const [editing, setEditing] = useState(() => Boolean(pendingLookup()));
  useEffect(() => {
    let mounted = true;
    void config()
      .then((c) => {
        if (mounted) setLookupEnabled(c.flightLookup === true);
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);
  const editButton = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => applyTheme(theme), [theme]);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [source, setSource] = useState("");
  const [origin, setOrigin] = useState<Airport | null>(null);
  const [dest, setDest] = useState<Airport | null>(null);
  const [departure, setDeparture] = useState("");
  const [airportQuery, setAirportQuery] = useState<RouteQuery | null>(null);
  const [result, setResult] = useState<RouteResult | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [retry, setRetry] = useState(0);
  const submitted = useRef<RouteQuery | null>(null);
  const meta =
    source === "latest"
      ? catalog?.latest
      : catalog?.replays.find((r) => r.runId === source);
  const coverage = selectedFlight
    ? scheduleCoverage(
        selectedFlight,
        meta,
        source === "latest",
        catalog?.replays ?? [],
        Date.now(),
      )
    : undefined;
  const reason = coverage?.issue ?? "";
  const query = useMemo<RouteQuery | null>(() => {
    if (!byNumber) return airportQuery;
    if (!selectedFlight || !source || reason) return null;
    return {
      origin: selectedFlight.departure.code,
      destination: selectedFlight.arrival.code,
      departure: selectedFlight.departure.time.utc,
      ...(selectedFlight.arrival.time && {
        arrival: selectedFlight.arrival.time.utc,
      }),
      run: source,
    };
  }, [byNumber, airportQuery, selectedFlight, source, reason]);
  const current = result?.query === query ? result : null;
  // Keep the open globe and layer controls when refreshing the same airport pair.
  const previousAirportForecast =
    !byNumber &&
    !current &&
    result &&
    "forecast" in result &&
    !result.byNumber &&
    query?.origin === result.query.origin &&
    query.destination === result.query.destination
      ? result.forecast
      : null;
  const forecast =
    current && "forecast" in current
      ? current.forecast
      : previousAirportForecast;
  const error =
    catalogError || (current && "error" in current ? current.error : "");
  const loading = !error && (!catalog || (!!query && !current));
  const [point, setPoint] = useState(0);
  const playback = useRoutePlayback(forecast?.samples, point, setPoint);
  const stopPlayback = playback.stop;
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
  useEffect(() => {
    stopPlayback();
    if (!query) return;
    const ctrl = new AbortController();
    void getJson<Forecast>(
      "/api/forecast",
      { ...query, wind: "1" },
      ctrl.signal,
    )
      .then((f) => {
        if (ctrl.signal.aborted) return;
        setPoint(Math.floor((f.samples.length - 1) / 2));
        setResult({ query, forecast: f, byNumber });
        if (submitted.current === query) setEditing(false);
      })
      .catch((e) => {
        if (!ctrl.signal.aborted)
          setResult({
            query,
            error:
              e instanceof Error
                ? e.message
                : "The forecast could not be loaded.",
          });
      });
    return () => ctrl.abort();
  }, [query, retry, stopPlayback, byNumber]);
  useLayoutEffect(() => {
    if (
      current &&
      "forecast" in current &&
      current.query === submitted.current
    ) {
      submitted.current = null;
      if (editButton.current?.offsetWidth)
        editButton.current.focus({ preventScroll: true });
    }
  }, [current]);
  useEffect(() => {
    const ctrl = new AbortController();
    setCatalogError("");
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
        const live =
          !!c.latest &&
          Date.parse(c.latest.validUntil) > Date.parse(c.serverTime) + 5400000;
        const run = live ? c.latest : c.replays[0];
        if (!run) throw new Error("No weather run is available yet.");
        const choice = live ? "latest" : run.runId;
        const when = defaultDeparture(run, live, c.serverTime);
        setCatalog(c);
        setSource(choice);
        setDeparture(when);
        setAirportQuery({
          origin: from.code,
          destination: to.code,
          departure: when + ":00Z",
          run: choice,
        });
      })
      .catch((e) => {
        if (!ctrl.signal.aborted) {
          setCatalogError(
            e instanceof Error ? e.message : "The app could not load.",
          );
        }
      });
    return () => ctrl.abort();
  }, [attempt]);
  function switchSource(selection: string) {
    if (!catalog) return;
    const run =
      selection === "latest"
        ? catalog.latest
        : catalog.replays.find((r) => r.runId === selection);
    if (!run) return;
    setSource(selection);
    if (byNumber) return;
    const when = defaultDeparture(
      run,
      selection === "latest",
      catalog.serverTime,
    );
    setDeparture(when);
    if (origin && dest)
      setAirportQuery({
        origin: origin.code,
        destination: dest.code,
        departure: when + ":00Z",
        run: selection,
      });
  }
  function selectSchedule(f: ScheduledFlight, archiveId?: string) {
    setSelectedFlight(f);
    if (archiveId) setSource(archiveId);
  }
  const dirty =
    forecast &&
    (forecast.origin.code !== origin?.code ||
      forecast.destination.code !== dest?.code ||
      forecast.departure.slice(0, 16) !== departure);
  const formExpanded = editing || (!forecast && !loading);
  const routeRecordings = recordingsByRoute(origin?.code, dest?.code);
  const themeAction =
    theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  const mobileSheet = useMedia("(max-width:43rem)");
  const timeline = forecast && (
    <Timeline
      forecast={forecast}
      index={point}
      onSelect={playback.select}
      observations={nearbyWeather}
      playing={playback.playing}
    />
  );
  return (
    <>
      <a href="#forecast" className="skip-link">
        Skip to forecast
      </a>
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
      <main id="forecast" tabIndex={-1} className="shell">
        <div className="page-title">
          <div>
            <h1>Flight forecast</h1>
            <p className="forecast-intro">
              European routes · 36-hour forecast window
              <a href="/recordings">Search recorded flights</a>
            </p>
          </div>
          {!catalog && loading && (
            <div
              className="source-control source-placeholder"
              aria-hidden="true"
            >
              <span />
            </div>
          )}
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
            data-awaiting-route={!forecast && loading}
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
            <div
              className="lookup-modes"
              role="group"
              aria-label="Search flights by"
            >
              <button
                type="button"
                aria-pressed={!byNumber}
                onClick={() => {
                  setSelectedFlight(null);
                  if (airportQuery) setSource(airportQuery.run);
                  setByNumber(false);
                  setEditing(true);
                }}
              >
                Airports
              </button>
              <button
                type="button"
                aria-pressed={byNumber}
                onClick={() => {
                  submitted.current = null;
                  setByNumber(true);
                  setEditing(true);
                }}
              >
                Flight number
              </button>
            </div>
            {byNumber ? (
              <div id="flight-form">
                <FlightLookup
                  run={meta}
                  live={source === "latest"}
                  selected={selectedFlight}
                  onMatch={setSelectedFlight}
                  onForecast={selectSchedule}
                  schedulesEnabled={lookupEnabled}
                  replays={catalog?.replays ?? []}
                />
              </div>
            ) : (
              <form
                id="flight-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!origin || !dest || !departure || !source) return;
                  const archive = archiveForDeparture(
                    meta,
                    source === "latest",
                    catalog?.replays ?? [],
                    departure + ":00Z",
                    Date.now(),
                  );
                  if (archive) setSource(archive.runId);
                  const next = {
                    origin: origin.code,
                    destination: dest.code,
                    departure: departure + ":00Z",
                    run: archive?.runId ?? source,
                  };
                  submitted.current = next;
                  setAirportQuery(next);
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
            )}
            {!byNumber && routeRecordings.length > 0 && (
              <section
                className="recording-matches"
                aria-label="Recorded flights on this route"
              >
                <h3>Recorded flights on this route</h3>
                <RecordingResults flights={routeRecordings} />
              </section>
            )}
            <div className="data-note" data-replay={source !== "latest"}>
              <Globe2 size={16} />
              <div>
                <b>{meta?.source || "NOAA GFS"}</b>
                <span>
                  {meta ? fmt(meta) : "European weather grid"}
                  {source && source !== "latest" ? " · Replay" : ""}
                </span>
              </div>
              {forecast &&
                !loading &&
                (!selectedFlight ||
                  Date.parse(selectedFlight.departure.time.utc) >
                    Date.now()) && (
                  <a
                    className="save-route-link"
                    href="/flights"
                    onClick={() =>
                      selectedFlight
                        ? keepFlight(selectedFlight)
                        : keepRoute(forecast)
                    }
                  >
                    {selectedFlight ? "Save flight" : "Save route"}
                  </a>
                )}
            </div>
          </section>
          <section
            className="map-card card"
            aria-label="Flight map"
            aria-busy={loading}
            data-awaiting-route={!forecast && loading && !error}
          >
            {(forecast || selectedFlight) && (
              <div className="map-title">
                <div>
                  {previousAirportForecast && (
                    <p role="status">Updating forecast…</p>
                  )}
                  {selectedFlight && (
                    <p className="scheduled-route-note">
                      {selectedFlight.number} ·{" "}
                      {forecast
                        ? "Estimated great-circle route · Cruise up to 35,000 ft"
                        : "Scheduled route"}
                    </p>
                  )}
                  <div className="route-codes">
                    <strong>
                      {selectedFlight?.departure.code ?? forecast?.origin.code}
                    </strong>
                    <ArrowRight size={20} />
                    <strong>
                      {selectedFlight?.arrival.code ??
                        forecast?.destination.code}
                    </strong>
                  </div>
                  <p>
                    {forecast
                      ? city(forecast.origin)
                      : selectedFlight?.departure.name}{" "}
                    to{" "}
                    {forecast
                      ? city(forecast.destination)
                      : selectedFlight?.arrival.name}
                  </p>
                </div>
                {forecast && (
                  <span className="route-stat">
                    <Plane size={14} />
                    {duration(forecast.durationMinutes)}
                    <i />
                    {forecast.distanceKm.toLocaleString("en-GB")} km
                  </span>
                )}
              </div>
            )}
            {forecast ? (
              <>
                <ForecastMap
                  forecast={forecast}
                  theme={theme}
                  selected={point}
                  onSelect={playback.select}
                  observations={visibleWeather}
                  weather={{
                    choice: layerChoice,
                    onChange: setLayerChoice,
                    data: weather.data,
                    loading: weather.loading,
                    error: weather.error,
                    onRetry: weather.retry,
                  }}
                />
                {mobileSheet && (
                  <FlightSheet level={forecast.peak}>{timeline}</FlightSheet>
                )}
                <div className="legend" aria-label="Intensity legend">
                  {forecastLevels.map((c) => (
                    <LevelButton key={c} level={c} marker />
                  ))}
                  {forecast.samples.some(
                    (s) => s.category === "unavailable",
                  ) && <LevelButton level="unavailable" marker />}
                </div>
                {forecast.mode === "replay" && !loading && (
                  <PlaybackControls
                    playback={playback}
                    current={forecast.samples[point]}
                    recorded={false}
                  />
                )}
              </>
            ) : selectedFlight && !loading ? (
              <ScheduledRoutePreview
                key={
                  selectedFlight.departure.code + selectedFlight.arrival.code
                }
                flight={selectedFlight}
                message={
                  error ||
                  (coverage?.replay
                    ? "An archived forecast covers this departure. Select View replay forecast to open it."
                    : reason)
                }
                onRetry={
                  error
                    ? () => {
                        if (catalogError) setAttempt((n) => n + 1);
                        else {
                          setResult(null);
                          setRetry((n) => n + 1);
                        }
                      }
                    : undefined
                }
              />
            ) : (
              <div className="empty-map" role={error ? "alert" : undefined}>
                {loading && <Skeleton label="Loading your route…" />}
                {!error && !loading && byNumber && (
                  <p>Find a flight or select a result to see its route.</p>
                )}
                {error && (
                  <span className="empty-icon">
                    <Navigation size={26} />
                  </span>
                )}
                {error && <h2>Forecast unavailable</h2>}
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
        {!mobileSheet && timeline}
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
