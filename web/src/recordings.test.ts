import { describe, expect, it } from "vitest";
import {
  recordingById,
  recordingsByNumber,
  recordingsByRoute,
  searchRecordings,
} from "./recordings";

describe("recorded flight search", () => {
  it("matches marketing numbers and observed callsigns on the departure airport's date", () => {
    for (const id of ["kl 1521", "KL-1521", "KLM71Z"]) {
      expect(recordingsByNumber(id, "2026-11-21").map((f) => f.number)).toEqual(
        ["KL1521"],
      );
      expect(recordingsByNumber(id, "2026-11-22")).toEqual([]);
    }
    expect(recordingsByNumber("KL15")).toEqual([]);
  });
  it("respects direction, airport aliases and optional date filters", () => {
    for (const q of [
      "MAN → TRN",
      "man-trn",
      "Manchester to Turin",
      "Manchester Turin",
      "Manchester Airport to Turin Airport",
    ]) {
      expect(searchRecordings(q).map((f) => f.number)).toEqual(["FR1800"]);
    }
    expect(searchRecordings("TRN MAN").map((f) => f.number)).toEqual([
      "FR1801",
    ]);
    expect(searchRecordings("AMS")).toHaveLength(3);
    expect(
      searchRecordings("El Prat", "2026-11-21").map((f) => f.number),
    ).toEqual(["KL1521"]);
    expect(searchRecordings("Amsterdam to Barcelona", "2026-11-22")).toEqual(
      [],
    );
    expect(searchRecordings("BCN to AMS")).toEqual([]);
  });
  it("keeps exact routes separate and rejects unrecognised recording ids", () => {
    expect(recordingsByRoute("CTA", "LIN").map((f) => f.number)).toEqual([
      "AZ1704",
    ]);
    expect(recordingsByRoute("LIN", "CTA")).toEqual([]);
    expect(recordingById("../archive")).toBeUndefined();
  });
});
