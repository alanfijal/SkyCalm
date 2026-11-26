import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Search } from "lucide-react";
import { config, signedIn, signIn } from "./passengerAuth";
import {
  airportTime,
  archiveForDeparture,
  findFlights,
  forecastIssue,
  localDate,
  type ScheduledFlight,
  type LookupResult,
} from "./flightSchedule";
import { keepFlight } from "./flightDraft";
import { RecordingResults } from "./RecordingResults";
import {
  recordingsByNumber,
  recordingsByRoute,
  replayLink,
  type RecordingEntry,
} from "./recordings";
import type { Run } from "./types";
import "./flightLookup.css";

import { pendingLookup, lookupKey as pendingKey } from "./lookupDraft";
export { pendingLookup } from "./lookupDraft";

export default function FlightLookup({
  run,
  live,
  onForecast,
  onSave,
  schedulesEnabled,
  replays,
}: {
  run: Run | null | undefined;
  live: boolean;
  onSave?: (f: ScheduledFlight) => void;
  onForecast?: (f: ScheduledFlight, archiveId?: string) => Promise<void>;
  replays: Run[];
  schedulesEnabled: boolean;
}) {
  const [number, setNumber] = useState(() => pendingLookup()?.number ?? "");
  const [date, setDate] = useState(() => pendingLookup()?.date ?? localDate());
  const [result, setResult] = useState<LookupResult | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [recordings, setRecordings] = useState<RecordingEntry[]>([]);
  const revision = useRef(0);
  function reset() {
    revision.current++;
    setResult(null);
    setRecordings([]);
    setError("");
    setBusy(false);
  }
  const search = useCallback(
    async (number: string, date: string, schedule = false) => {
      const current = ++revision.current;
      setBusy(true);
      setResult(null);
      setError("");
      try {
        const archived = recordingsByNumber(number, date);
        setRecordings(archived);
        if (archived.length && !schedule) return;
        const settings = await config();
        if (current !== revision.current) return;
        if (!settings.flightLookup) {
          setError(
            "No recording matches that flight and date. Schedule lookup is unavailable.",
          );
          return;
        }
        if (settings.auth && !signedIn()) {
          sessionStorage.setItem(
            pendingKey,
            JSON.stringify({
              number,
              date,
              schedule,
              until: Date.now() + 600000,
            }),
          );
          await signIn(settings.auth, "/forecast");
          return;
        }
        const response = await findFlights(archived[0]?.number ?? number, date);
        if (current === revision.current) setResult(response);
      } catch (e) {
        if (current === revision.current)
          setError(
            e instanceof Error ? e.message : "Flight lookup is unavailable.",
          );
      } finally {
        if (current === revision.current) setBusy(false);
      }
    },
    [],
  );
  useEffect(() => {
    const saved = pendingLookup();
    try {
      sessionStorage.removeItem(pendingKey);
    } catch {
      /* Airport and archive searches also work when browser storage is blocked. */
    }
    if (saved && (signedIn() || saved.fromLanding))
      void search(saved.number, saved.date, saved.schedule);
    return () => {
      revision.current++;
    };
  }, [search]);
  const otherDates = recordingsByNumber(number).filter(
    (f) => f.localDate !== date,
  );
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
      {otherDates.length > 0 && (
        <section
          className="recording-matches"
          aria-label="Recordings on other dates"
        >
          <h3>Other recorded dates</h3>
          <RecordingResults flights={otherDates} />
        </section>
      )}
      {recordings.length > 0 && (
        <section
          className="recording-matches"
          aria-label="Matching recordings"
          aria-live="polite"
        >
          <h3>Recorded flight</h3>
          <RecordingResults flights={recordings} />
          {schedulesEnabled && !result && (
            <button
              type="button"
              className="guide-button"
              disabled={busy}
              onClick={() => void search(number, date, true)}
            >
              Check schedule details
            </button>
          )}
        </section>
      )}
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
            const now = Date.now();
            const archived = archiveForDeparture(
              run,
              live,
              replays,
              f.departure.time.utc,
              now,
            );
            const reason = forecastIssue(
              f,
              archived ?? run,
              live && !archived,
              now,
            );
            const recordedLegs = recordingsByNumber(
              f.number,
              f.departure.time.local.slice(0, 10),
            ).filter(
              (r) =>
                r.origin.code === f.departure.code &&
                r.destination.code === f.arrival.code,
            );
            const otherLegs = recordingsByRoute(
              f.departure.code,
              f.arrival.code,
            ).some((r) => !recordedLegs.includes(r));
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
                {recordedLegs
                  .filter((r) => !recordings.includes(r))
                  .map((r) => (
                    <a key={r.id} href={replayLink(r.id)}>
                      Replay this recorded flight
                    </a>
                  ))}
                {otherLegs && (
                  <a
                    href={
                      "/recordings?q=" +
                      encodeURIComponent(
                        f.departure.code + " to " + f.arrival.code,
                      )
                    }
                  >
                    Past recordings on this route
                  </a>
                )}
                {onForecast &&
                  (reason ? (
                    <p>{reason}</p>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setError("");
                        void onForecast(f, archived?.runId).catch((e) =>
                          setError(
                            e instanceof Error
                              ? e.message
                              : "Could not load the forecast.",
                          ),
                        );
                      }}
                    >
                      {live && !archived
                        ? "View forecast"
                        : "View replay forecast"}
                    </button>
                  ))}
                {canSave && onSave && (
                  <button type="button" onClick={() => onSave(f)}>
                    Use this flight
                  </button>
                )}
                {canSave && !onSave && (
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
