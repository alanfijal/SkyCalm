import type { Forecast } from "./types";
const key = "skycalm-flight-draft";
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
export function draft() {
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
      };
  } catch {
    /* The form also works without a saved route. */
  }
  return null;
}
export function clearDraft() {
  sessionStorage.removeItem(key);
}
