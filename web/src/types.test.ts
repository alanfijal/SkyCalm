import { describe, expect, it } from "vitest";
import { clock, defaultDeparture, duration, type Run } from "./types";

const run: Run = {
  runId: "gfs-20261124-12",
  issued: "2026-11-24T12:00:00Z",
  validUntil: "2026-11-26T00:00:00Z",
  source: "NOAA",
  scorer: "ti1-cape-v1",
};
describe("forecast controls", () => {
  it("pins the departure to replay time on another day", () => {
    expect(defaultDeparture(run, false, "2030-01-01T10:00:00Z")).toBe(
      "2026-11-24T18:00",
    );
  });
  it("uses the next half hour after the live lead-in", () => {
    expect(defaultDeparture(run, true, "2026-11-24T19:02:00Z")).toBe(
      "2026-11-24T20:30",
    );
  });
  it("formats UTC and minute carry across an hour", () => {
    expect(clock("2026-11-24T20:30:00+01:00")).toBe("19:30");
    expect(duration(59.8)).toBe("1h");
    expect(duration(90)).toBe("1h 30m");
  });
});
