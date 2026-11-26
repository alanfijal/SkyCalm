import { describe, expect, it } from "vitest";
import { airportZone, clocks, wallCandidates } from "./journey";
describe("passenger clocks", () => {
  it("resolves Madrid times across both daylight-saving transitions", () => {
    expect(wallCandidates("2026-03-29T02:30", "Europe/Madrid")).toEqual([]);
    expect(wallCandidates("2026-10-25T02:30", "Europe/Madrid")).toEqual([
      "2026-10-25T00:30:00.000Z",
      "2026-10-25T01:30:00.000Z",
    ]);
    expect(wallCandidates("2026-07-01T12:30", "Europe/Madrid")).toEqual([
      "2026-07-01T10:30:00.000Z",
    ]);
  });
  it("uses the airport rather than the viewer’s clock", () => {
    expect(airportZone("EDI")).toBe("Europe/London");
    expect(airportZone("JCU")).toBe("Africa/Ceuta");
    expect(clocks("2026-07-01T10:30:00Z", "BCN")).toContain("12:30 BCN local");
    expect(clocks("2026-07-01T10:30:00Z", "BCN", "utc")).toMatch(
      /10:30 UTC.*12:30 BCN local/,
    );
  });
});
