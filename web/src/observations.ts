import type { Sample } from "./types";

export type Coord = [number, number];
type Geometry =
  | { type: "Point"; coordinates: Coord }
  | { type: "Polygon"; coordinates: Coord[][] }
  | { type: "MultiPolygon"; coordinates: Coord[][][] };
export interface WeatherItem {
  id: string;
  kind: "sigmet" | "report";
  source: string;
  from: string;
  to: string | null;
  intensity: string;
  codes: string[];
  baseFt: number | null;
  topFt: number | null;
  geometry: Geometry;
}
export interface WeatherSnapshot {
  asOf: string;
  source: string;
  mode: "live" | "replay";
  stale: boolean;
  limited: boolean;
  items: WeatherItem[];
}
export interface LayerChoice {
  sigmet: boolean;
  report: boolean;
}

export function contains(ring: Coord[], x: number, y: number) {
  let hit = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [ax, ay] = ring[i],
      [bx, by] = ring[j];
    if (ay > y !== by > y && x < ((bx - ax) * (y - ay)) / (by - ay) + ax)
      hit = !hit;
  }
  return hit;
}
export function nearby(items: WeatherItem[], point: Sample): WeatherItem[] {
  const at = Date.parse(point.at),
    rad = Math.PI / 180;
  return items.filter((item) => {
    const from = Date.parse(item.from);
    if (item.kind === "report" && item.geometry.type === "Point") {
      if (
        Math.abs(at - from) > 45 * 60000 ||
        (item.baseFt !== null &&
          Math.abs(point.altitudeFt - item.baseFt) > 3000)
      )
        return false;
      const [lon, lat] = item.geometry.coordinates;
      const a =
        Math.sin(((point.lat - lat) * rad) / 2) ** 2 +
        Math.cos(point.lat * rad) *
          Math.cos(lat * rad) *
          Math.sin(((point.lon - lon) * rad) / 2) ** 2;
      return 12742 * Math.asin(Math.sqrt(Math.min(1, a))) <= 75;
    }
    if (
      item.kind !== "sigmet" ||
      item.geometry.type === "Point" ||
      at < from ||
      !item.to ||
      at >= Date.parse(item.to) ||
      (item.baseFt !== null && point.altitudeFt < item.baseFt) ||
      (item.topFt !== null && point.altitudeFt > item.topFt)
    )
      return false;
    const pieces =
      item.geometry.type === "Polygon"
        ? [item.geometry.coordinates]
        : item.geometry.coordinates;
    return pieces.some(
      (p) =>
        p.length > 0 &&
        contains(p[0], point.lon, point.lat) &&
        !p.slice(1).some((ring) => contains(ring, point.lon, point.lat)),
    );
  });
}
