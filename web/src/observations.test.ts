import { expect, test } from "vitest";
import { nearby, type WeatherItem } from "./observations";
import type { Sample } from "./types";

const pt = {
  lat: 52,
  lon: 2,
  at: "2026-11-21T15:00:00Z",
  altitudeFt: 34000,
} as Sample;
const report: WeatherItem = {
  id: "a",
  kind: "report",
  source: "AIREP",
  from: "2026-11-21T14:45:00Z",
  to: null,
  intensity: "light",
  codes: ["LGT"],
  baseFt: 33000,
  topFt: 33000,
  geometry: { type: "Point", coordinates: [2.01, 52.02] },
};
const sig: WeatherItem = {
  ...report,
  id: "s",
  kind: "sigmet",
  from: "2026-11-21T14:06:00Z",
  to: "2026-11-21T18:00:00Z",
  baseFt: 20000,
  topFt: 40000,
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [1, 51],
        [3, 51],
        [3, 53],
        [1, 53],
        [1, 51],
      ],
    ],
  },
};
test("match advisories and pilot reports at the selected place, time and altitude", () => {
  expect(nearby([report, sig], pt)).toEqual([report, sig]);
  expect(nearby([report, sig], { ...pt, altitudeFt: 15000 })).toEqual([]);
  expect(nearby([report, sig], { ...pt, at: "2026-11-21T19:00:00Z" })).toEqual(
    [],
  );
  expect(nearby([report, sig], { ...pt, lon: 8 })).toEqual([]);
});
