import { expect, it } from "vitest";
import { forecastIssue, type ScheduledFlight } from "./flightSchedule";

const grid = {
  runId: "gfs-20300214-00",
  issued: "2030-02-14T00:00:00Z",
  validUntil: "2030-02-15T12:00:00Z",
  source: "NOAA GFS",
  scorer: "physics",
};
const now = Date.parse("2030-02-15T08:00:00Z");
const leg: ScheduledFlight = {
  number: "XY480",
  status: "Expected",
  aircraft: null,
  departure: {
    code: "BRU",
    name: "Brussels",
    covered: true,
    time: { utc: "2030-02-15T15:40:00Z", local: "2030-02-15T16:40+01:00" },
  },
  arrival: { code: "HAM", name: "Hamburg", covered: true, time: null },
};
function at(utc: string): ScheduledFlight {
  return {
    ...leg,
    departure: { ...leg.departure, time: { ...leg.departure.time, utc } },
  };
}
it("explains the forecast time limit and treats both endpoints as inclusive", () => {
  expect(forecastIssue(leg, grid, true, now)).toBe(
    "This forecast ends 15 Feb at 12:00 UTC. The flight departs 15 Feb at 15:40 UTC.",
  );
  expect(forecastIssue(at(grid.validUntil), grid, true, now)).toBe("");
  expect(forecastIssue(at(grid.issued), grid, false, now)).toBe("");
  expect(forecastIssue(at("2030-02-13T23:59:00Z"), grid, false, now)).toContain(
    "begins on 14 Feb at 00:00 UTC",
  );
  expect(forecastIssue(at(grid.issued), grid, true, now)).toContain(
    "departure has passed",
  );
});
it("keeps unavailable data, geography and cancelled schedules distinct", () => {
  expect(forecastIssue(leg, null, true, now)).toBe(
    "No weather forecast is available for this departure.",
  );
  expect(
    forecastIssue(
      { ...leg, arrival: { ...leg.arrival, covered: false } },
      grid,
      true,
      now,
    ),
  ).toContain("European forecast area");
  expect(forecastIssue({ ...leg, status: "Cancelled" }, grid, true, now)).toBe(
    "This flight is cancelled.",
  );
});
