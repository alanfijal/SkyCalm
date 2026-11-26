import zones from "./airportZones.json";
import type { Category, Forecast } from "./types";

export interface Flight {
  slot: number;
  id: string;
  revision: string;
  flightNumber?: string;
  arrivalScheduled?: boolean;
  origin: string;
  destination: string;
  departure: string;
  arrival: string;
  watch: string;
  assessment?: { peak: Category };
  baseline?: { peak: Category };
  ribbon?: Category[];
  forecastAt?: number;
  nextReminder?: number | null;
  expiresAt?: number;
}
export interface Notice {
  noticeId: string;
  kind: string;
  created: number;
  delivery: string;
  peak?: Category;
  slot?: number;
  deliveredAt?: number;
  deliveredLevel?: Category | null;
  isRead?: boolean;
  routeLabel?: string;
  flightId?: string;
  flightRevision?: string;
  runMarker?: string;
}
export interface Preferences {
  email: boolean;
  push: boolean;
  explainAlerts?: boolean;
  sensitivity?: "all" | "moderate";
  nervousFlyer?: boolean;
  altitudeUnit?: "ft" | "m";
  timeDisplay?: "local" | "utc";
  homeAirport?: string;
  quietHours?: { start: string; end: string; zone: string } | null;
}
export interface HistoryPoint {
  marker: string;
  at: number;
  peak: Category;
  run?: string;
  issued?: string;
  simulated?: boolean;
}
export interface Detail {
  flight: Flight;
  forecast: Forecast | null;
  history: HistoryPoint[];
  shareUntil: number | null;
  recap: null | {
    status: string;
    captures?: number;
    reports: {
      observed: string;
      reported: Category;
      forecast: Category;
      elapsed_minutes: number;
    }[];
  };
}
export const levels: Category[] = ["smooth", "light", "moderate", "severe"];
export const airportZone = (code: string) =>
  (zones as Record<string, string>)[code];
export function wallTime(iso: string, zone: string) {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(iso))
      .map((x) => [x.type, x.value]),
  );
  return p.year + "-" + p.month + "-" + p.day + "T" + p.hour + ":" + p.minute;
}
export function wallCandidates(wall: string, zone: string): string[] {
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(wall)) return [];
  const t = Date.parse(wall + "Z");
  if (!Number.isFinite(t)) return [];
  const offsets = new Set<number>();
  for (const hours of [-36, 0, 36]) {
    const at = t + hours * 3600000;
    offsets.add(
      Date.parse(wallTime(new Date(at).toISOString(), zone) + "Z") - at,
    );
  }
  return [...offsets]
    .map((delta) => new Date(t - delta).toISOString())
    .filter((iso) => wallTime(iso, zone) === wall)
    .sort();
}
export function clocks(
  iso: string,
  code: string,
  primary: "local" | "utc" = "local",
) {
  const label = (zone: string) =>
    new Intl.DateTimeFormat("en-GB", {
      timeZone: zone,
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).format(new Date(iso));
  const zone = airportZone(code);
  const utc = label("UTC") + " UTC";
  if (!zone) return utc;
  const local = label(zone) + " " + code + " local";
  return primary === "utc" ? utc + " · " + local : local + " · " + utc;
}
export function relative(ms: number) {
  const minutes = Math.floor(Math.abs(ms) / 60000);
  return minutes < 60
    ? minutes + " min"
    : minutes < 1440
      ? Math.floor(minutes / 60) + " h"
      : Math.floor(minutes / 1440) + " d";
}
export function countdown(f: Flight, now: number) {
  if (Date.parse(f.arrival) <= now) return "Arrived";
  const diff = Date.parse(f.departure) - now;
  return diff <= 0 ? "In flight" : "Departs in " + relative(diff);
}
export const flightHref = (id: string) =>
  "/flights?flight=" + encodeURIComponent(id);
export const noticeNames: Record<string, string> = {
  "forecast-change": "Forecast changed",
  "reminder-24h": "24 hours until departure",
  "reminder-3h": "3 hours until departure",
  "test-change": "Demo forecast changed",
  "test-push": "Test notification",
};
