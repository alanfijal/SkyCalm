import { useEffect, useState } from "react";
import { ArrowLeft, Pause, Play, RotateCcw } from "lucide-react";
import RouteGlobe from "./RouteGlobe";
import Timeline from "./Timeline";
import { forecastLevels, LevelButton } from "./CabinGuide";
import { clock, duration, fetchWithRetry, type Forecast } from "./types";
import type { WeatherItem } from "./observations";
import "./recordedFlight.css";

const base = "/data/recorded-flight/az1704-20261121";
const speed = 120;
const noObservations: WeatherItem[] = [];

interface Recording extends Forecast {
  flightNumber: string;
  callsign: string;
  positions: number;
  sourceUrl: string;
  licenseUrl: string;
}

function Player({ flight }: { flight: Recording }) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const samples = flight.samples;
  const current = samples[index];
  const last = index === samples.length - 1;
  const theme =
    document.documentElement.dataset.theme === "light" ? "light" : "dark";
  const date = new Intl.DateTimeFormat("en-GB", {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(flight.departure));

  useEffect(() => {
    if (!playing || last) return;
    const delay =
      (Date.parse(samples[index + 1].at) - Date.parse(samples[index].at)) /
      speed;
    const timer = window.setTimeout(() => {
      setIndex(index + 1);
      if (index + 1 === samples.length - 1) setPlaying(false);
    }, delay);
    return () => window.clearTimeout(timer);
  }, [index, last, playing, samples]);

  function select(i: number) {
    setPlaying(false);
    setIndex(i);
  }
  function togglePlay() {
    if (last) setIndex(0);
    setPlaying(!playing);
  }

  return (
    <>
      <div className="page-title">
        <div>
          <h1>Catania to Milan Linate</h1>
          <p>
            ITA Airways {flight.flightNumber} · {date} · Recorded flight
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
        <RouteGlobe
          theme={theme}
          samples={samples}
          origin={flight.origin}
          destination={flight.destination}
          selected={index}
          onSelect={select}
          observations={noObservations}
        />
        <div className="legend" aria-label="Forecast intensity legend">
          <b>Forecast</b>
          {forecastLevels.map((c) => (
            <LevelButton key={c} level={c} marker />
          ))}
        </div>
        <div className="recording-controls">
          <button type="button" onClick={togglePlay}>
            {playing ? (
              <Pause size={16} />
            ) : last ? (
              <RotateCcw size={16} />
            ) : (
              <Play size={16} />
            )}
            {playing ? "Pause replay" : last ? "Play again" : "Play replay"}
          </button>
          <span className="recording-speed">
            <span className="sr-only">Playback speed </span>
            {speed}×
          </span>
          <time dateTime={current.at}>{clock(current.at)} UTC</time>
          <span>{current.altitudeFt.toLocaleString("en-GB")} ft</span>
        </div>
      </section>
      <Timeline
        forecast={flight}
        index={index}
        onSelect={select}
        observations={null}
        playing={playing}
      />
      <footer className="recording-sources">
        <p>
          <a href={flight.sourceUrl}>ADSB.lol</a> recorded {flight.positions}{" "}
          positions and barometric altitudes for {flight.callsign}. Colours show
          the NOAA GFS turbulence forecast issued at {clock(flight.run.issued)}{" "}
          UTC that day.
        </p>
        <p>
          <a href={base + ".csv"} download>
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

export default function RecordedFlight() {
  const [flight, setFlight] = useState<Recording | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetchWithRetry(base + ".json", 8000, controller.signal)
      .then(async (response) => {
        if (!response.ok) throw Error("Recording unavailable");
        const data: Recording = await response.json();
        if (!data.samples?.length) throw Error("Recording has no positions");
        if (!controller.signal.aborted) setFlight(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [attempt]);
  return (
    <>
      <header className="topbar">
        <div className="nav-inner">
          <a href="/" className="brand">
            <img src="/skycalm.svg" width="32" height="32" alt="" />
            SkyCalm
          </a>
          <a href="/" className="guide-button">
            <ArrowLeft size={16} /> Flight forecast
          </a>
        </div>
      </header>
      <main className="shell recording">
        {flight ? (
          <Player flight={flight} />
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
          <p role="status">Loading the recorded flight…</p>
        )}
      </main>
    </>
  );
}
