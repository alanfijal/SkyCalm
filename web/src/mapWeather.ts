import type { FeatureCollection, LineString, Polygon } from "geojson";

const radians = Math.PI / 180;
export function solarPosition(iso: string) {
  // NOAA fractional-year approximation, using the selected flight time in UTC.
  const d = new Date(iso),
    year = d.getUTCFullYear(),
    start = Date.UTC(year, 0, 1);
  const days = (Date.UTC(year + 1, 0, 1) - start) / 86400000;
  const g = ((2 * Math.PI) / days) * ((d.getTime() - start) / 86400000 - 0.5);
  const eq =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(g) -
      0.032077 * Math.sin(g) -
      0.014615 * Math.cos(2 * g) -
      0.040849 * Math.sin(2 * g));
  const dec =
    0.006918 -
    0.399912 * Math.cos(g) +
    0.070257 * Math.sin(g) -
    0.006758 * Math.cos(2 * g) +
    0.000907 * Math.sin(2 * g) -
    0.002697 * Math.cos(3 * g) +
    0.00148 * Math.sin(3 * g);
  const minutes =
    d.getUTCHours() * 60 + d.getUTCMinutes() + d.getUTCSeconds() / 60;
  return { declination: dec, longitude: (720 - minutes - eq) / 4 };
}
export function nightArea(iso: string): FeatureCollection<Polygon> {
  const sun = solarPosition(iso),
    pole = sun.declination >= 0 ? -85 : 85;
  const slope = Math.tan(sun.declination) || 1e-12;
  const edge = (lon: number) =>
    Math.max(
      -85,
      Math.min(
        85,
        Math.atan(-Math.cos((lon - sun.longitude) * radians) / slope) / radians,
      ),
    );
  // Independent longitude strips also close correctly at the antimeridian.
  const features: FeatureCollection<Polygon>["features"] = [];
  for (let start = -180; start < 180; start += 30) {
    const ring: number[][] = [[start, pole]];
    for (let x = start; x <= start + 30; x += 2) ring.push([x, edge(x)]);
    ring.push([start + 30, pole], [start, pole]);
    features.push({
      type: "Feature",
      properties: {},
      geometry: { type: "Polygon", coordinates: [ring] },
    });
  }
  return { type: "FeatureCollection", features };
}
export function windLead(issued: string, at: string) {
  const hours = (Date.parse(at) - Date.parse(issued)) / 3600000;
  return Number.isFinite(hours) && hours >= 0 && hours <= 36
    ? Math.round(hours / 3)
    : -1;
}
export function windLines(frame: string): FeatureCollection<LineString> {
  const bytes = Int8Array.from(atob(frame), (c) => c.charCodeAt(0));
  const cols = 18,
    rows = 10;
  if (bytes.length !== cols * rows * 2) throw Error("Invalid cruise wind grid");
  function velocity(lon: number, lat: number) {
    const x = (lon + 25) / 4,
      y = (lat - 34) / 4,
      i = Math.floor(x),
      j = Math.floor(y);
    if (i < 0 || j < 0 || i >= cols - 1 || j >= rows - 1) return;
    let u = 0,
      v = 0;
    for (const [dx, dy] of [
      [0, 0],
      [1, 0],
      [0, 1],
      [1, 1],
    ]) {
      const k = ((j + dy) * cols + i + dx) * 2,
        w = (dx ? x - i : 1 - x + i) * (dy ? y - j : 1 - y + j);
      if (bytes[k] === -128 || bytes[k + 1] === -128) return;
      u += bytes[k] * w;
      v += bytes[k + 1] * w;
    }
    return [u, v];
  }
  const features: FeatureCollection<LineString>["features"] = [];
  for (let j = 0; j < rows - 1; j++)
    for (let i = 0; i < cols - 1; i++) {
      let x = -24 + 4 * i,
        y = 35 + 4 * j;
      const initial = velocity(x, y);
      if (!initial || Math.hypot(...initial) < 4) continue;
      const points = [[x, y]];
      for (let s = 0; s < 7; s++) {
        const v = velocity(x, y);
        if (!v) break;
        x += (v[0] * 850) / (111200 * Math.cos(y * radians));
        y += (v[1] * 850) / 111200;
        points.push([x, y]);
      }
      if (points.length > 1)
        features.push({
          type: "Feature",
          properties: { speed: Math.round(Math.hypot(...initial)) },
          geometry: { type: "LineString", coordinates: points },
        });
    }
  return { type: "FeatureCollection", features };
}
