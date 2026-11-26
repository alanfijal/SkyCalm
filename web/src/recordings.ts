import recordings from "./recordingIndex.json";

export type RecordingEntry = (typeof recordings)[number];
type Stop = RecordingEntry["origin"];
export const defaultRecordingId = "az1704-20261121";

export function replayLink(id: string) {
  return "/replay?flight=" + encodeURIComponent(id);
}

export function recordingById(id: string) {
  return recordings.find((flight) => flight.id === id);
}

function normalize(value: string) {
  return value.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
}

function flightCode(value: string) {
  return normalize(value).replace(/[\s-]+/g, "");
}

export function recordingsByNumber(number: string, localDate?: string) {
  const code = flightCode(number);
  return recordings.filter(
    (f) =>
      [f.number, f.callsign].some((n) => flightCode(n) === code) &&
      (!localDate || f.localDate === localDate),
  );
}

export function recordingsByRoute(origin?: string, destination?: string) {
  return recordings.filter(
    (f) => f.origin.code === origin && f.destination.code === destination,
  );
}

function matchesStop(stop: Stop, words: string[]) {
  const name = normalize([stop.code, stop.city, stop.name].join(" "));
  return words.every((word) => name.includes(word));
}

export function searchRecordings(query: string, date = "") {
  const q = normalize(query);
  const words = q.split(/\s+/);
  const pair = q
    .replace(/^([a-z]{3})-([a-z]{3})$/, "$1→$2")
    .split(/\s*(?:→|->|[–—]|\bto\b|\s-\s)\s*/);
  return recordings.filter((r) => {
    if (date && r.localDate !== date) return false;
    if (!q) return true;
    if (pair.length > 1) {
      return (
        pair.length === 2 &&
        matchesStop(r.origin, pair[0].split(/\s+/)) &&
        matchesStop(r.destination, pair[1].split(/\s+/))
      );
    }
    if (
      [r.number, r.callsign].some((s) =>
        flightCode(s).startsWith(flightCode(q)),
      )
    )
      return true;
    if (
      normalize(r.airline).includes(q) ||
      matchesStop(r.origin, words) ||
      matchesStop(r.destination, words)
    )
      return true;
    return words.some(
      (_, i) =>
        i > 0 &&
        matchesStop(r.origin, words.slice(0, i)) &&
        matchesStop(r.destination, words.slice(i)),
    );
  });
}
