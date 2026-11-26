import { Skeleton } from "./PageSkeleton";
import { useEffect, useState } from "react";
import { ArrowLeft, ChevronRight, Share2 } from "lucide-react";
import Timeline from "./Timeline";
import { guide, knownLevel, LevelButton, LevelText } from "./CabinGuide";
import { categoryColor } from "./theme";
import { config, privateApi } from "./passengerAuth";
import {
  airportZone,
  clocks,
  countdown,
  levels,
  noticeNames,
  relative,
} from "./journey";
import type {
  Detail,
  Flight,
  HistoryPoint,
  Notice,
  Preferences,
} from "./journey";
import type { Category, Forecast } from "./types";
import "./journey.css";

export function Ribbon({ bands }: { bands: Category[] }) {
  return (
    <div
      className="journey-ribbon"
      role="img"
      aria-label={
        bands.length
          ? "Route conditions from departure to arrival: " + bands.join(", ")
          : "Route forecast pending"
      }
    >
      {(bands.length ? bands : ["unavailable" as Category]).map((level, i) => (
        <i key={i} style={{ background: categoryColor(level) }} />
      ))}
    </div>
  );
}
export function FlightSummary({
  flight: f,
  prefs,
  now,
}: {
  flight: Flight;
  prefs: Preferences;
  now: number;
}) {
  const peak = f.assessment?.peak,
    base = f.baseline?.peak;
  const trend =
    peak && base ? levels.indexOf(peak) - levels.indexOf(base) : undefined;
  return (
    <div className="journey-summary">
      <small>
        {countdown(f, now)}
        {f.watch === "demo" ? " · Classroom replay" : ""}
      </small>
      <h3>
        {f.flightNumber && <span>{f.flightNumber} · </span>}
        {f.origin} <ChevronRight size={16} /> {f.destination}
      </h3>
      <p>{clocks(f.departure, f.origin, prefs.timeDisplay)}</p>
      <Ribbon bands={f.ribbon ?? []} />
      <div className="journey-line">
        {peak && knownLevel(peak) ? (
          <LevelButton level={peak} />
        ) : (
          <span>Forecast pending</span>
        )}
        {trend !== undefined && (
          <small>
            {trend > 0 ? "Rougher" : trend < 0 ? "Calmer" : "Unchanged"} since
            first forecast
          </small>
        )}
      </div>
      {f.forecastAt && (
        <small>Updated {relative(now - f.forecastAt * 1000)} ago</small>
      )}
      {f.nextReminder && (
        <p>
          Next reminder ·{" "}
          {clocks(
            new Date(f.nextReminder * 1000).toISOString(),
            f.origin,
            prefs.timeDisplay,
          )}
        </p>
      )}
    </div>
  );
}
function ForecastView({
  forecast: f,
  prefs = { email: false, push: false },
}: {
  forecast: Forecast | null;
  prefs?: Preferences;
}) {
  const [index, setIndex] = useState(0);
  if (!f)
    return <p>A route forecast appears when a weather run covers departure.</p>;
  const i = Math.min(index, f.samples.length - 1);
  if (i < 0) return <p>No route samples are available.</p>;
  const sample = f.samples[i],
    unit = prefs.altitudeUnit ?? "ft";
  const alt = (feet: number) =>
    Math.round(unit === "ft" ? feet : feet * 0.3048).toLocaleString("en-GB") +
    " " +
    unit;
  const cells = Object.entries(f.altitudeBands ?? {}).reverse();
  return (
    <>
      <div className="journey-forecast">
        <Timeline
          forecast={f}
          index={i}
          onSelect={setIndex}
          observations={null}
          altitudeUnit={unit}
          timeZone={
            prefs.timeDisplay === "utc" ? "UTC" : airportZone(f.origin.code)
          }
        />
      </div>
      <section className="pass-card">
        <h2>Altitude along the route</h2>
        <p>
          Compare forecast conditions at cruising heights. Use the time slider
          to inspect each section.
        </p>
        {cells.map(([ft, bands]) => (
          <div className="altitude-row" key={ft}>
            <span>{alt(Number(ft))}</span>
            <Ribbon bands={bands} />
          </div>
        ))}
        <svg
          viewBox="0 0 500 70"
          preserveAspectRatio="none"
          className="altitude-profile"
          role="img"
          aria-label="Estimated flight altitude from departure to arrival"
        >
          <polyline
            points={f.samples
              .map((s, j) =>
                [
                  (j * 496) / Math.max(1, f.samples.length - 1) + 2,
                  64 - (s.altitudeFt / 40000) * 58,
                ].join(","),
              )
              .join(" ")}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        <label>
          Flight time · {Math.round(sample.elapsedMinutes)} min · estimated{" "}
          {alt(sample.altitudeFt)}
          <input
            type="range"
            min={0}
            max={f.samples.length - 1}
            value={i}
            onChange={(e) => setIndex(Number(e.target.value))}
          />
        </label>
        {cells.length > 0 && (
          <p>
            {cells
              .map(
                ([ft, bands]) =>
                  alt(Number(ft)) + " " + guide.levels[bands[i]].label,
              )
              .join(" · ")}
          </p>
        )}
      </section>
      {prefs.nervousFlyer && (
        <section className="pass-card">
          <h2>What it may feel like</h2>
          <p>
            <LevelText text={guide.levels[f.peak].summary} />
          </p>
          <p>{guide.seatbelt}</p>
        </section>
      )}
    </>
  );
}
function HistoryChart({
  history,
  notices,
}: {
  history: HistoryPoint[];
  notices: Notice[];
}) {
  const sent = notices.filter(
    (n) => n.delivery === "push" || n.delivery === "email",
  );
  const events = [
    ...history.map((h) => ({
      at: h.at,
      level: h.peak,
      text: h.simulated ? "Classroom change" : (h.run ?? "Forecast run"),
      alert: false,
    })),
    ...sent.map((n) => ({
      at: n.deliveredAt ?? n.created,
      level: n.peak,
      text: noticeNames[n.kind] ?? "Flight alert",
      alert: true,
    })),
  ].sort((a, b) => a.at - b.at);
  if (!events.length) return <p>The first scored run will start this chart.</p>;
  const start = events[0].at,
    end = events.at(-1)!.at;
  const x = (at: number) =>
    end === start ? 240 : 15 + (450 * (at - start)) / (end - start);
  const y = (p: Category) => 101 - 25 * levels.indexOf(p);
  return (
    <>
      <svg
        className="history-plot"
        viewBox="0 0 480 135"
        role="img"
        aria-label="Expected peak by forecast run; diamonds mark sent alerts"
      >
        {levels.map((p) => (
          <line
            key={p}
            x1="12"
            x2="470"
            y1={y(p)}
            y2={y(p)}
            stroke="var(--border)"
          />
        ))}
        <polyline
          points={history.map((h) => x(h.at) + "," + y(h.peak)).join(" ")}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2"
        />
        {events.map((e, i) =>
          e.alert ? (
            <path
              key={i}
              transform={`translate(${x(e.at)} 122)`}
              d="M0 -5L5 0L0 5L-5 0Z"
              fill="var(--text)"
            >
              <title>{e.text}</title>
            </path>
          ) : (
            <circle
              key={i}
              cx={x(e.at)}
              cy={y(e.level!)}
              r="5"
              fill={categoryColor(e.level!)}
            />
          ),
        )}
      </svg>
      <ol className="history-events">
        {events
          .slice()
          .reverse()
          .map((e, i) => (
            <li key={i}>
              <time>
                {new Date(e.at * 1000).toLocaleString("en-GB", {
                  timeZone: "UTC",
                  day: "numeric",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                })}{" "}
                UTC
              </time>
              <span>
                {e.alert ? "◆ Alert sent" : "● " + guide.levels[e.level!].label}{" "}
                · {e.text}
              </span>
            </li>
          ))}
      </ol>
    </>
  );
}
export function Journey({
  flight,
  notices,
  prefs,
}: {
  flight: Flight;
  notices: Notice[];
  prefs: Preferences;
}) {
  const [data, setData] = useState<Detail | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [link, setLink] = useState(""),
    [active, setActive] = useState(0),
    [copied, setCopied] = useState(false);
  const url = "/api/me/flights/" + flight.slot;
  useEffect(() => {
    let alive = true;
    privateApi<Detail>(url + "/detail")
      .then((d) => {
        if (alive) {
          setData(d);
          setActive(d.shareUntil ?? 0);
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [url, flight.id, flight.revision, flight.forecastAt]);
  async function share(create: boolean) {
    setError("");
    setBusy(true);
    setCopied(false);
    try {
      const r = await privateApi<{
        token?: string;
        preview?: string;
        expiresAt?: number;
      }>(url + "/share", create ? "POST" : "DELETE", {
        revision: flight.revision,
      });
      const view = r.preview
        ? new URL(
            "/family/" + r.preview,
            (await config()).apiOrigin || location.origin,
          ).href
        : location.origin + "/shared";
      setLink(r.token ? view + "#" + r.token : "");
      setActive(r.expiresAt ?? 0);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <a href="/flights">
        <ArrowLeft size={15} /> Saved flights
      </a>
      <section className="pass-card">
        <FlightSummary flight={flight} prefs={prefs} now={Date.now()} />
      </section>
      {error && <p role="alert">{error}</p>}
      {!data ? (
        <Skeleton label="Loading flight details…" />
      ) : (
        <>
          <ForecastView forecast={data.forecast} prefs={prefs} />
          <section className="pass-card">
            <h2>Forecast history</h2>
            <HistoryChart
              history={data.history}
              notices={notices.filter(
                (n) =>
                  !n.flightRevision || n.flightRevision === flight.revision,
              )}
            />
          </section>
          {data.recap && (
            <section className="pass-card">
              <h2>After landing</h2>
              <p>
                {data.recap.status === "no-forecast"
                  ? "No saved forecast was available for comparison."
                  : data.recap.status === "no-captures"
                    ? "No weather capture covers this flight."
                    : data.recap.reports.length
                      ? "Nearby pilot reports and the forecast at the same route section."
                      : "No qualifying turbulence reports in the available captures. The cabin conditions remain unknown."}
              </p>
              {data.recap.reports.map((r, i) => (
                <p key={i}>
                  {r.elapsed_minutes} min · Forecast {r.forecast} · Reported{" "}
                  {r.reported}
                </p>
              ))}
              {flight.expiresAt && (
                <small>
                  Available until{" "}
                  {clocks(
                    new Date(flight.expiresAt * 1000).toISOString(),
                    flight.destination,
                    prefs.timeDisplay,
                  )}
                </small>
              )}
            </section>
          )}
          <section className="pass-card">
            <h2>
              <Share2 size={17} /> Share with family
            </h2>
            <p>
              Anyone with your link can view this flight’s route, times and
              forecast for up to 24 hours. Messaging apps can preview the route,
              departure date and peak category.
            </p>
            {active > Date.now() / 1000 && (
              <p>
                Link expires{" "}
                {clocks(
                  new Date(active * 1000).toISOString(),
                  flight.origin,
                  prefs.timeDisplay,
                )}
                .
              </p>
            )}
            {link && (
              <label>
                Family link
                <input
                  readOnly
                  value={link}
                  onFocus={(e) => e.target.select()}
                />
              </label>
            )}
            <div className="pass-actions">
              {link && (
                <button
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(link);
                      setCopied(true);
                    } catch {
                      setError("Select the link above and copy it.");
                    }
                  }}
                >
                  {copied ? "Copied" : "Copy link"}
                </button>
              )}
              <button disabled={busy} onClick={() => void share(true)}>
                {active > Date.now() / 1000
                  ? "Replace link"
                  : "Create family link"}
              </button>
              {active > Date.now() / 1000 && (
                <button disabled={busy} onClick={() => void share(false)}>
                  Revoke link
                </button>
              )}
            </div>
          </section>
        </>
      )}
    </>
  );
}
export function SharedFlight() {
  const [token] = useState(() => location.hash.slice(1)),
    [result, setResult] = useState<{
      flight: Flight;
      forecast: Forecast | null;
      expiresAt: number;
    }>(),
    [error, setError] = useState("");
  useEffect(() => {
    let alive = true,
      loading = false;
    let expiry: ReturnType<typeof setTimeout>;
    const ctrl = new AbortController();
    history.replaceState(null, "", "/shared");
    async function check() {
      if (loading || document.visibilityState === "hidden") return;
      loading = true;
      try {
        if (!/^[a-f0-9]{32}\.[a-f0-9]{64}$/.test(token))
          throw Error("Open the complete link sent by the passenger.");
        const c = await config();
        const r = await fetch(c.apiOrigin + "/api/shared", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ token }),
          credentials: "omit",
          referrerPolicy: "no-referrer",
          cache: "no-store",
          signal: AbortSignal.any([ctrl.signal, AbortSignal.timeout(15000)]),
        });
        const d = await r.json();
        if (!r.ok) throw Error(d.message ?? "The link is unavailable.");
        if (alive) {
          setError("");
          setResult(d);
          clearTimeout(expiry);
          expiry = setTimeout(
            () => {
              setResult(undefined);
              setError("This family link has expired.");
            },
            Math.max(0, d.expiresAt * 1000 - Date.now()),
          );
        }
      } catch (e) {
        if (alive) {
          setResult(undefined);
          setError(e instanceof Error ? e.message : "The link is unavailable.");
        }
      } finally {
        loading = false;
      }
    }
    void check();
    document.addEventListener("visibilitychange", check);
    return () => {
      alive = false;
      ctrl.abort();
      clearTimeout(expiry);
      document.removeEventListener("visibilitychange", check);
    };
  }, [token]);
  return (
    <main className="passenger-page">
      <header className="pass-nav">
        <a className="brand" href="/">
          SkyCalm
        </a>
      </header>
      <div className="pass-shell">
        <h1>Shared forecast</h1>
        {error ? (
          <section className="pass-card">
            <p role="alert">{error}</p>
            <a href="/forecast">Explore a flight forecast</a>
          </section>
        ) : result ? (
          <>
            <section className="pass-card">
              <h2>
                {result.flight.origin} → {result.flight.destination}
              </h2>
              <p>{clocks(result.flight.departure, result.flight.origin)}</p>
              <p>
                Available until{" "}
                {clocks(
                  new Date(result.expiresAt * 1000).toISOString(),
                  result.flight.origin,
                )}
              </p>
            </section>
            <ForecastView forecast={result.forecast} />
          </>
        ) : (
          <Skeleton label="Opening the shared forecast…" />
        )}
      </div>
    </main>
  );
}
