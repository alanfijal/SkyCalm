export type Category =
  "smooth" | "light" | "moderate" | "severe" | "unavailable";
export const COLORS: Record<Category, string> = {
  smooth: "#7be2c6",
  light: "#9fc6ff",
  moderate: "#f4bf76",
  severe: "#eb8ca9",
  unavailable: "#8394a3",
};
export const LABELS: Record<Category, string> = {
  smooth: "Smooth",
  light: "Light",
  moderate: "Moderate",
  severe: "Severe",
  unavailable: "Unavailable",
};
export interface Airport {
  code: string;
  name: string;
  city: string;
  country: string;
  lat: number;
  lon: number;
  elevationFt?: number | null;
}
export interface Run {
  runId: string;
  issued: string;
  validUntil: string;
  source: string;
  scorer: string;
}
export interface Catalog {
  latest: Run | null;
  replays: Run[];
  serverTime: string;
}
export interface Sample {
  lat: number;
  lon: number;
  altitudeFt: number;
  elapsedMinutes: number;
  distanceKm: number;
  at: string;
  category: Category;
  method: string;
  ti1: number | null;
  shear: number | null;
  cape: number | null;
  phase: "climb" | "cruise" | "descent";
}
export interface Forecast {
  origin: Airport;
  destination: Airport;
  run: Run;
  mode: "live" | "replay";
  departure: string;
  distanceKm: number;
  durationMinutes: number;
  peak: Category;
  samples: Sample[];
}
export const city = (a: Airport) => a.city || a.name;
export const clock = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
export const dateLabel = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
  }).format(new Date(iso));
export function duration(minutes: number) {
  const whole = Math.round(minutes);
  if (whole < 60) return `${whole} min`;
  return whole % 60
    ? `${Math.floor(whole / 60)}h ${whole % 60}m`
    : `${Math.floor(whole / 60)}h`;
}
export function defaultDeparture(run: Run, live: boolean, now: string) {
  const issued = Date.parse(run.issued);
  const time = live
    ? Math.max(
        issued,
        Math.ceil((Date.parse(now) + 3600000) / 1800000) * 1800000,
      )
    : issued + 6 * 3600000;
  return new Date(time).toISOString().slice(0, 16);
}
let originRequest: Promise<string> | undefined;
export async function fetchWithRetry(
  url: string | URL,
  timeoutMs: number,
  signal?: AbortSignal,
): Promise<Response> {
  const once = () => {
    signal?.throwIfAborted();
    const timeout = AbortSignal.timeout(timeoutMs);
    return fetch(url, {
      cache: "no-store",
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  };
  try {
    const first = await once();
    if (first.status !== 429 && first.status < 500) return first;
    await first.body?.cancel();
  } catch (error) {
    if (signal?.aborted) throw error;
  }
  await new Promise((resolve) =>
    setTimeout(resolve, 250 + Math.random() * 100),
  );
  return once();
}

function apiOrigin(): Promise<string> {
  if (!originRequest) {
    originRequest = fetchWithRetry("/config.json", 8000)
      .then(async (result) => {
        if (!result.ok)
          throw new Error("The forecast configuration could not be loaded.");
        const config = await result.json();
        if (typeof config.apiOrigin !== "string")
          throw new Error("Invalid forecast configuration.");
        return config.apiOrigin;
      })
      .catch((error) => {
        originRequest = undefined;
        throw error;
      });
  }
  return originRequest;
}

export async function getJson<T>(
  path: string,
  params: Record<string, string> = {},
  signal?: AbortSignal,
): Promise<T> {
  const configured = await apiOrigin();
  const url = new URL(configured + path, window.location.origin);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const res = await fetchWithRetry(url, 12000, signal);
  const data = await res.json();
  if (!res.ok)
    throw new Error(data.message || "The forecast could not be loaded.");
  return data as T;
}
