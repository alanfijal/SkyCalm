import { config, privateApi } from "./passengerAuth";
import { clock, dateLabel, type Run } from "./types";

export interface ScheduleTime {
  utc: string;
  local: string;
}
export interface Stop {
  code: string;
  name: string;
  covered: boolean;
  time: ScheduleTime | null;
}
export interface ScheduledFlight {
  number: string;
  departure: Stop & { time: ScheduleTime };
  arrival: Stop;
  aircraft: string | null;
  status: string;
}
export interface LookupResult {
  flights: ScheduledFlight[];
  checkedAt: number;
  cached: boolean;
}

export function archiveForDeparture(
  selected: Run | null | undefined,
  live: boolean,
  replays: Run[],
  departure: string,
  now: number,
): Run | undefined {
  const when = Date.parse(departure);
  const covers = (r: Run) =>
    Date.parse(r.issued) <= when && when <= Date.parse(r.validUntil);
  if (
    selected &&
    covers(selected) &&
    (!live || (when >= now - 300000 && now <= Date.parse(selected.validUntil)))
  )
    return;
  return replays
    .filter(covers)
    .sort((a, b) => Date.parse(b.issued) - Date.parse(a.issued))[0];
}

export async function findFlights(
  number: string,
  date: string,
): Promise<LookupResult> {
  const settings = await config();
  const path = "/api/me/flight-lookup",
    body = { number, date };
  if (settings.auth) return privateApi<LookupResult>(path, "POST", body);
  if (!["localhost", "127.0.0.1"].includes(location.hostname))
    throw Error("Flight-number lookup is unavailable.");
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(12000),
  });
  const result = await r.json();
  if (!r.ok)
    throw Error(result.message ?? "Flight-number lookup is unavailable.");
  return result;
}

export function forecastIssue(
  f: ScheduledFlight,
  run: Run | null | undefined,
  live: boolean,
  now: number,
): string {
  if (!f.departure.covered || !f.arrival.covered)
    return "Outside the European forecast area.";
  if (f.departure.code === f.arrival.code)
    return "The departure and arrival airports are the same.";
  if (["canceled", "cancelled"].includes(f.status.toLowerCase()))
    return "This flight is cancelled.";
  if (!run) return "No weather forecast is available for this departure.";
  const timestamp = (iso: string) => `${dateLabel(iso)} at ${clock(iso)} UTC`;
  const when = Date.parse(f.departure.time.utc);
  if (when > Date.parse(run.validUntil))
    return `This forecast ends ${timestamp(run.validUntil)}. The flight departs ${timestamp(f.departure.time.utc)}.`;
  if (when < Date.parse(run.issued))
    return `This flight departs before this forecast begins on ${timestamp(run.issued)}.`;
  if (live && (when < now - 300000 || now > Date.parse(run.validUntil)))
    return "This departure has passed. An archived forecast is needed.";
  return "";
}

export function scheduleCoverage(
  f: ScheduledFlight,
  run: Run | null | undefined,
  live: boolean,
  replays: Run[],
  now: number,
) {
  const issue = forecastIssue(f, run, live, now);
  const replay = issue
    ? archiveForDeparture(run, live, replays, f.departure.time.utc, now)
    : undefined;
  return {
    issue,
    replay:
      replay && !forecastIssue(f, replay, false, now) ? replay : undefined,
  };
}

export function localDate(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}

// Format the airport's own clock, independently of the browser's timezone.
export function airportTime(value: ScheduleTime): string {
  const wall = value.local.slice(0, 16);
  const fmt = (iso: string) =>
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "UTC",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).format(new Date(iso));
  return fmt(wall + "Z") + " local · " + fmt(value.utc) + " UTC";
}
