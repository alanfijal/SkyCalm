import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Search } from "lucide-react";
import { config, signedIn, signIn } from "./passengerAuth";
import {
  airportTime,
  findFlights,
  forecastIssue,
  localDate,
  type ScheduledFlight,
  type LookupResult,
} from "./flightSchedule";
import { keepFlight } from "./flightDraft";
import type { Run } from "./types";
import "./flightLookup.css";

const pendingKey = "skycalm-pending-lookup";
export function pendingLookup(): { number: string; date: string } | null {
  try {
    const x = JSON.parse(sessionStorage.getItem(pendingKey) || "null");
    return x &&
      x.until > Date.now() &&
      typeof x.number === "string" &&
      typeof x.date === "string"
      ? x
      : null;
  } catch {
    return null;
  }
}

export default function FlightLookup({
  run,
  live,
  onForecast,
}: {
  run: Run | null | undefined;
  live: boolean;
  onForecast: (f: ScheduledFlight) => Promise<void>;
}) {
  const [number, setNumber] = useState(() => pendingLookup()?.number ?? "");
  const [date, setDate] = useState(() => pendingLookup()?.date ?? localDate());
  const [result, setResult] = useState<LookupResult | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const revision = useRef(0);
  function reset() {
    revision.current++;
    setResult(null);
    setError("");
    setBusy(false);
  }
  const search = useCallback(async (number: string, date: string) => {
    const current = ++revision.current;
    setBusy(true);
    setResult(null);
    setError("");
    try {
      const settings = await config();
      if (current !== revision.current) return;
      if (settings.auth && !signedIn()) {
        sessionStorage.setItem(
          pendingKey,
          JSON.stringify({ number, date, until: Date.now() + 600000 }),
        );
        await signIn(settings.auth, "/");
        return;
      }
      const response = await findFlights(number, date);
      if (current === revision.current) setResult(response);
    } catch (e) {
      if (current === revision.current)
        setError(
          e instanceof Error ? e.message : "Flight lookup is unavailable.",
        );
    } finally {
      if (current === revision.current) setBusy(false);
    }
  }, []);
  useEffect(() => {
    const saved = pendingLookup();
    sessionStorage.removeItem(pendingKey);
    if (saved && signedIn()) void search(saved.number, saved.date);
    return () => {
      revision.current++;
    };
  }, [search]);
  return (
    <div className="flight-lookup">
      <form
        aria-label="Flight number search"
        onSubmit={(e) => {
          e.preventDefault();
          const fields = new FormData(e.currentTarget);
          const flightNumber = String(fields.get("number") ?? "").toUpperCase();
          const departureDate = String(fields.get("date") ?? "");
          setNumber(flightNumber);
          setDate(departureDate);
          void search(flightNumber, departureDate);
        }}
      >
        <label>
          Flight number
          <input
            name="number"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            required
            placeholder="IB3204"
            maxLength={12}
            value={number}
            onChange={(e) => {
              reset();
              setNumber(e.target.value.toUpperCase());
            }}
          />
        </label>
        <label>
          Departure date (local)
          <input
            name="date"
            type="date"
            required
            value={date}
            onChange={(e) => {
              reset();
              setDate(e.target.value);
            }}
          />
        </label>
        <button className="submit" disabled={busy || !number.trim() || !date}>
          <Search size={16} />
          {busy ? "Searching…" : "Find flight"}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && (
        <div aria-live="polite">
          {!result.flights.length && (
            <p>
              No matching flight was found for this departure date. Try another
              date or search by airports.
            </p>
          )}
          {result.flights.map((f) => {
            const reason = forecastIssue(f, run, live, Date.now());
            const canSave =
              f.departure.covered &&
              f.arrival.covered &&
              Date.parse(f.departure.time.utc) > Date.now() &&
              !["cancelled", "canceled"].includes(f.status.toLowerCase());
            return (
              <article
                className="schedule-card"
                key={f.departure.code + f.arrival.code + f.departure.time.utc}
              >
                <h3>
                  {f.number} <span>{f.status}</span>
                </h3>
                <strong className="schedule-pair">
                  {f.departure.code}
                  <ArrowRight size={15} />
                  {f.arrival.code}
                </strong>
                <dl>
                  {[f.departure, f.arrival].map((stop, i) => (
                    <div key={i}>
                      <dt>
                        {i ? "Arrival" : "Departure"} · {stop.name}
                      </dt>
                      <dd>
                        {stop.time
                          ? airportTime(stop.time)
                          : "Scheduled time unavailable"}
                      </dd>
                    </div>
                  ))}
                  <div>
                    <dt>Aircraft</dt>
                    <dd>{f.aircraft ?? "Not listed"}</dd>
                  </div>
                </dl>
                {reason ? (
                  <p>{reason}</p>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setError("");
                      void onForecast(f).catch((e) =>
                        setError(
                          e instanceof Error
                            ? e.message
                            : "Could not load the forecast.",
                        ),
                      );
                    }}
                  >
                    {live ? "View forecast" : "View replay forecast"}
                  </button>
                )}
                {canSave && (
                  <a href="/flights" onClick={() => keepFlight(f)}>
                    Save to My flights
                  </a>
                )}
              </article>
            );
          })}
          <p className="schedule-source">
            Schedules from{" "}
            <a
              href="https://aerodatabox.com/"
              target="_blank"
              rel="noopener"
              referrerPolicy="strict-origin"
            >
              AeroDataBox
            </a>
          </p>
        </div>
      )}
    </div>
  );
}
