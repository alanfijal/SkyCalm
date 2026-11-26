import { Play } from "lucide-react";
import { replayLink, type RecordingEntry } from "./recordings";
import { clock } from "./types";
import "./recordingSearch.css";

export function RecordingResults({ flights }: { flights: RecordingEntry[] }) {
  return (
    <ul className="recording-results">
      {flights.map((f) => (
        <li key={f.id}>
          <a href={replayLink(f.id)}>
            <span>
              <strong>
                {f.origin.city} → {f.destination.city}
              </strong>
              <small>
                {f.number} · {f.origin.code} → {f.destination.code}
              </small>
              <small>
                {new Intl.DateTimeFormat("en-GB", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                  timeZone: "UTC",
                }).format(new Date(f.localDate + "T12:00:00Z"))}{" "}
                · {clock(f.first)} UTC
              </small>
            </span>
            <Play size={17} aria-hidden="true" />
            <span className="sr-only">Play recording</span>
          </a>
        </li>
      ))}
    </ul>
  );
}
