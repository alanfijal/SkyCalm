import { useState } from "react";
import AirportField from "./AirportField";
import FlightLookup from "./FlightLookup";
import type { FlightForm } from "./flightDraft";
import type { ScheduledFlight } from "./flightSchedule";
import { airportZone, clocks, wallCandidates, wallTime } from "./journey";
import { airportLabel } from "./PassengerSettings";

export default function JourneyForm({
  initial,
  edit,
  busy,
  schedules,
  onSave,
  onCancel,
}: {
  initial: FlightForm;
  edit: boolean;
  busy: boolean;
  schedules: boolean;
  onSave: (data: FlightForm) => void;
  onCancel: () => void;
}) {
  const [mode, setMode] = useState<"airports" | "number">("airports"),
    [form, setForm] = useState(initial);
  const [origin, setOrigin] = useState(airportLabel(initial.origin)),
    [destination, setDestination] = useState(airportLabel(initial.destination));
  const [zoneMode, setZoneMode] = useState<"local" | "utc">("local");
  const zone =
    zoneMode === "utc" ? "UTC" : (airportZone(origin?.code ?? "") ?? "UTC");
  const [wall, setWall] = useState(
    initial.departure ? wallTime(initial.departure + "Z", zone) : "",
  );
  const candidates = wallCandidates(wall, zone);
  const [fold, setFold] = useState(
    initial.departure ? new Date(initial.departure + "Z").toISOString() : "",
  );
  const utc =
    candidates.length === 1
      ? candidates[0]
      : candidates.includes(fold)
        ? fold
        : "";
  function picked(f: ScheduledFlight) {
    const a = f.departure,
      b = f.arrival;
    setOrigin(airportLabel(a.code));
    setDestination(airportLabel(b.code));
    setZoneMode("local");
    setWall(wallTime(a.time.utc, airportZone(a.code) ?? "UTC"));
    setFold(new Date(a.time.utc).toISOString());
    setForm({
      origin: a.code,
      destination: b.code,
      departure: a.time.utc.slice(0, 16),
      flightNumber: f.number,
      scheduledArrival: b.time?.utc,
    });
    setMode("airports");
  }
  function manual() {
    setForm({ ...form, flightNumber: undefined, scheduledArrival: undefined });
    setFold("");
  }
  return (
    <section className="pass-card">
      <h3>{form.flightNumber ?? (edit ? "Edit flight" : "Add a flight")}</h3>
      {!edit && schedules && (
        <div className="pass-actions">
          <button
            aria-pressed={mode === "airports"}
            onClick={() => setMode("airports")}
          >
            By airports
          </button>
          <button
            aria-pressed={mode === "number"}
            onClick={() => setMode("number")}
          >
            By flight number
          </button>
        </div>
      )}
      {mode === "number" ? (
        <FlightLookup
          run={null}
          live={false}
          onSave={picked}
          replays={[]}
          schedulesEnabled={schedules}
        />
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (origin && destination && utc)
              onSave({
                ...form,
                origin: origin.code,
                destination: destination.code,
                departure: utc.slice(0, 16),
              });
          }}
        >
          <div className="settings-grid">
            <AirportField
              label="Departure airport"
              selected={origin}
              onChange={(a) => {
                setOrigin(a);
                manual();
              }}
            />
            <AirportField
              label="Arrival airport"
              selected={destination}
              onChange={(a) => {
                setDestination(a);
                manual();
              }}
            />
          </div>
          <div className="settings-grid">
            <label>
              Departure time
              <input
                type="datetime-local"
                required
                value={wall}
                onChange={(e) => {
                  setWall(e.target.value);
                  manual();
                }}
              />
            </label>
            <label>
              Enter time in
              <select
                value={zoneMode}
                onChange={(e) => {
                  const v = e.target.value as "local" | "utc";
                  setZoneMode(v);
                  if (utc)
                    setWall(
                      wallTime(
                        utc,
                        v === "utc"
                          ? "UTC"
                          : (airportZone(origin?.code ?? "") ?? "UTC"),
                      ),
                    );
                }}
              >
                <option value="local">
                  {origin ? origin.code + " local" : "Departure airport local"}
                </option>
                <option value="utc">UTC</option>
              </select>
            </label>
          </div>
          {candidates.length === 2 && (
            <label>
              This clock time occurs twice
              <select value={utc} onChange={(e) => setFold(e.target.value)}>
                <option value="">Choose the departure</option>
                {candidates.map((t) => (
                  <option key={t} value={t}>
                    {t.slice(11, 16)} UTC
                  </option>
                ))}
              </select>
            </label>
          )}
          {wall && origin && !candidates.length && (
            <p role="alert">
              This local time does not exist. Choose a different time or enter
              UTC.
            </p>
          )}
          {utc && origin && <p>{clocks(utc, origin.code)}</p>}
          <div className="pass-actions">
            <button
              disabled={busy || !origin || !destination || !utc}
              className="pass-primary"
            >
              Save flight
            </button>
            <button type="button" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
