import type { ScheduledFlight } from "./flightSchedule";
import type { Forecast } from "./types";
const key = "skycalm-flight-draft";
export interface FlightForm {
  origin: string;
  destination: string;
  departure: string;
  flightNumber?: string;
  scheduledArrival?: string;
}
export function keepFlight(f: ScheduledFlight) {
  const form: FlightForm = {
    origin: f.departure.code,
    destination: f.arrival.code,
    departure: f.departure.time.utc.slice(0, 16),
    flightNumber: f.number,
    ...(f.arrival.time ? { scheduledArrival: f.arrival.time.utc } : {}),
  };
  sessionStorage.setItem(
    key,
    JSON.stringify({ ...form, until: Date.now() + 600000 }),
  );
}
export function keepRoute(f: Forecast) {
  const date =
    Date.parse(f.departure) > Date.now() ? f.departure.slice(0, 16) : "";
  sessionStorage.setItem(
    key,
    JSON.stringify({
      origin: f.origin.code,
      destination: f.destination.code,
      departure: date,
      until: Date.now() + 600000,
    }),
  );
}
export function draft(): FlightForm | null {
  try {
    const item = JSON.parse(sessionStorage.getItem(key) ?? "null");
    if (
      item &&
      item.until > Date.now() &&
      [item.origin, item.destination].every(
        (c) => typeof c === "string" && /^[A-Z]{3}$/.test(c),
      )
    )
      return {
        origin: item.origin as string,
        destination: item.destination as string,
        departure: typeof item.departure === "string" ? item.departure : "",
        ...(typeof item.flightNumber === "string"
          ? { flightNumber: item.flightNumber }
          : {}),
        ...(typeof item.scheduledArrival === "string"
          ? { scheduledArrival: item.scheduledArrival }
          : {}),
      };
  } catch {
    /* The form also works without a saved route. */
  }
  return null;
}
export function clearDraft() {
  sessionStorage.removeItem(key);
}
