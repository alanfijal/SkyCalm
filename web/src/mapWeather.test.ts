import { describe, it, expect } from "vitest";
import { nightArea, solarPosition, windLead, windLines } from "./mapWeather";

describe("flight-time daylight", () => {
  it("puts the equinox sun near Greenwich at noon and the night side over the Pacific", () => {
    const at = "2026-03-20T12:00:00Z",
      sun = solarPosition(at);
    expect(Math.abs(sun.longitude)).toBeLessThan(3);
    expect(Math.abs(sun.declination)).toBeLessThan(0.02);
    const strips = nightArea(at).features;
    expect(strips).toHaveLength(12);
    for (const f of strips) {
      const ring = f.geometry.coordinates[0];
      expect(ring[0]).toEqual(ring.at(-1));
      expect(
        ring.every(([x, y]) => Math.abs(x) <= 180 && Math.abs(y) <= 85),
      ).toBe(true);
    }
    const midnight = solarPosition("2026-03-20T00:00:00Z");
    expect(Math.abs(midnight.longitude - sun.longitude)).toBeCloseTo(180, 0);
    expect(solarPosition("2026-06-21T12:00:00Z").declination).toBeGreaterThan(
      0.39,
    );
    expect(solarPosition("2026-12-21T12:00:00Z").declination).toBeLessThan(
      -0.39,
    );
  });
});
describe("250 hPa forecast winds", () => {
  const issue = "2026-11-21T06:00:00Z";
  it("selects the nearest available three-hour lead within its run", () => {
    expect(windLead(issue, "2026-11-21T07:31:00Z")).toBe(1);
    expect(windLead(issue, "2026-11-22T18:00:00Z")).toBe(12);
    expect(windLead(issue, "2026-11-22T18:01:00Z")).toBe(-1);
    expect(windLead(issue, "2026-11-21T05:59:00Z")).toBe(-1);
  });
  it("draws eastward winds east, without interpolating through missing or calm data", () => {
    const frame = (u: number, v: number) =>
      btoa(
        String.fromCharCode(
          ...Array.from({ length: 360 }, (_, i) => (i % 2 ? v : u) & 255),
        ),
      );
    const lines = windLines(frame(20, 0)).features;
    expect(lines.length).toBeGreaterThan(100);
    for (const f of lines) {
      const [[x, y], to] = f.geometry.coordinates;
      expect(to[0]).toBeGreaterThan(x);
      expect(to[1]).toBe(y);
    }
    expect(windLines(frame(-128, 0)).features).toHaveLength(0);
    expect(windLines(frame(0, 0)).features).toHaveLength(0);
    expect(() => windLines("AAAA")).toThrow();
  });
});
