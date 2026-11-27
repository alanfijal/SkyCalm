import { useEffect, useState } from "react";
import { RoutePrint, type PrintPoint } from "./RoutePrint";
import { type ScheduledFlight } from "./flightSchedule";
import { getJson, type Airport } from "./types";

export function ScheduledRoutePreview({
  flight,
  message,
  onRetry,
}: {
  flight: ScheduledFlight;
  message: string;
  onRetry?: () => void;
}) {
  const from = flight.departure.code,
    to = flight.arrival.code;
  const inArea =
    flight.departure.covered && flight.arrival.covered && from !== to;
  const [points, setPoints] = useState<PrintPoint[]>([]);
  useEffect(() => {
    if (!inArea) return;
    const ctrl = new AbortController();
    void Promise.all(
      [from, to].map(async (code) => {
        const { airports } = await getJson<{ airports: Airport[] }>(
          "/api/airports",
          { q: code },
          ctrl.signal,
        );
        return airports.find((a) => a.code === code);
      }),
    )
      .then(([a, b]) => {
        if (!ctrl.signal.aborted && a && b)
          setPoints(
            [a, b].map(({ lat, lon }) => ({
              lat,
              lon,
              category: "unavailable",
            })),
          );
      })
      .catch(() => {
        /* The timetable and coverage message also work without coordinates. */
      });
    return () => ctrl.abort();
  }, [from, to, inArea]);
  return (
    <div className="scheduled-preview">
      {inArea && points.length === 2 && (
        <RoutePrint
          from={from}
          to={to}
          samples={points}
          label={`Airport locations: ${from} to ${to}, direct line`}
        />
      )}
      <div className="empty-map">
        <h2>Schedule only</h2>
        <p>{message}</p>
        {onRetry && (
          <button type="button" onClick={onRetry}>
            Retry forecast
          </button>
        )}
      </div>
    </div>
  );
}
