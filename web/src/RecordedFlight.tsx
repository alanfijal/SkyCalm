import { Skeleton } from "./PageSkeleton";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { ForecastMap } from "./ForecastMap";
import { FlightSheet } from "./FlightSheet";
import { useMedia } from "./useMedia";
import Timeline from "./Timeline";
import { forecastLevels, LevelButton } from "./CabinGuide";
import {
  clock,
  dateLabel,
  duration,
  fetchWithRetry,
  type Forecast,
} from "./types";
import type { WeatherItem } from "./observations";
import {
  defaultRecordingId,
  recordingById,
  type RecordingEntry,
} from "./recordings";
import { PlaybackControls, useRoutePlayback } from "./RoutePlayback";

const noObservations: WeatherItem[] = [];

interface Recording extends Forecast {
  flightNumber: string;
  callsign: string;
  positions: number;
  sourceUrl: string;
  licenseUrl: string;
}

function Player({
  flight,
  entry,
}: {
  flight: Recording;
  entry: RecordingEntry;
}) {
  const [index, setIndex] = useState(0);
  const samples = flight.samples;
  const current = samples[index];
  const playback = useRoutePlayback(samples, index, setIndex);
  const theme =
    document.documentElement.dataset.theme === "light" ? "light" : "dark";
  const mobileSheet = useMedia("(max-width:43rem)");
  const timeline = (
    <Timeline
      forecast={flight}
      index={index}
      onSelect={playback.select}
      observations={null}
      playing={playback.playing}
    />
  );
  const date = new Intl.DateTimeFormat("en-GB", {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(entry.localDate + "T12:00:00Z"));

  return (
    <>
      <div className="page-title">
        <div>
          <h1>
            {entry.origin.city} to {entry.destination.city}
          </h1>
          <p>
            {entry.airline} {flight.flightNumber} · {date} · Recorded flight
          </p>
        </div>
      </div>
      <section className="map-card card" aria-label="Recorded flight map">
        <div className="map-title">
          <div className="route-codes">
            <strong>
              {flight.origin.code} → {flight.destination.code}
            </strong>
          </div>
          <span className="route-stat">
            {duration(flight.durationMinutes)} ·{" "}
            {flight.distanceKm.toLocaleString("en-GB")} km recorded
          </span>
        </div>
        <ForecastMap
          forecast={flight}
          theme={theme}
          selected={index}
          onSelect={playback.select}
          observations={noObservations}
        />
        {mobileSheet && (
          <FlightSheet level={flight.peak}>{timeline}</FlightSheet>
        )}
        <div className="legend" aria-label="Forecast intensity legend">
          <b>Forecast</b>
          {forecastLevels.map((c) => (
            <LevelButton key={c} level={c} marker />
          ))}
        </div>
        <PlaybackControls playback={playback} current={current} recorded />
      </section>
      {!mobileSheet && timeline}
      <footer className="recording-sources">
        <p>
          <a href={flight.sourceUrl}>ADSB.lol</a> recorded {flight.positions}{" "}
          positions and barometric altitudes for {flight.callsign}. Colours show
          the NOAA GFS turbulence forecast issued on{" "}
          {dateLabel(flight.run.issued)} at {clock(flight.run.issued)} UTC.
        </p>
        <p>
          <a href={"/data/recorded-flight/" + entry.id + ".csv"} download>
            Download recorded positions (CSV)
          </a>
          {" · "}
          <a href={flight.licenseUrl}>Open Database License 1.0</a>
        </p>
        <p>For passenger education only.</p>
      </footer>
    </>
  );
}

export default function RecordedFlight({ id }: { id: string | null }) {
  const entry = recordingById(id ?? defaultRecordingId);
  const [flight, setFlight] = useState<Recording | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!entry) return;
    const controller = new AbortController();
    fetchWithRetry(
      "/data/recorded-flight/" + entry.id + ".json",
      8000,
      controller.signal,
    )
      .then(async (response) => {
        if (!response.ok) throw Error("Recording unavailable");
        const data: Recording = await response.json();
        if (
          !data.samples?.length ||
          data.callsign !== entry.callsign ||
          data.departure !== entry.first
        )
          throw Error("Recording does not match this flight");
        if (!controller.signal.aborted) setFlight(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [attempt, entry]);
  return (
    <>
      <header className="topbar">
        <div className="nav-inner">
          <a href="/" className="brand" aria-label="SkyCalm home">
            <img src="/skycalm.svg" width="32" height="32" alt="" />
            SkyCalm
          </a>
          <nav className="replay-nav" aria-label="Main navigation">
            <a
              href="/forecast"
              className="guide-button"
              aria-label="Flight forecast"
            >
              Forecast
            </a>
            <a href="/recordings" className="guide-button">
              <ArrowLeft size={16} /> Recorded flights
            </a>
          </nav>
        </div>
      </header>
      <main className="shell recording">
        {!entry ? (
          <div className="empty-map" role="alert">
            <h1>Recording not found</h1>
            <a href="/recordings">Search recorded flights</a>
          </div>
        ) : flight ? (
          <Player flight={flight} entry={entry} />
        ) : failed ? (
          <div className="empty-map" role="alert">
            <h1>Recording unavailable</h1>
            <button
              onClick={() => {
                setFailed(false);
                setAttempt((a) => a + 1);
              }}
            >
              Try again
            </button>
          </div>
        ) : (
          <Skeleton label="Loading the recorded flight…" />
        )}
      </main>
    </>
  );
}
