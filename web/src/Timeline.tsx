import { Clock3, Mountain, Wind } from "lucide-react";
import { COLORS, LABELS, clock, duration } from "./types";
import type { Forecast } from "./types";

export default function Timeline({
  forecast,
  index,
  onSelect,
}: {
  forecast: Forecast;
  index: number;
  onSelect: (i: number) => void;
}) {
  const { samples, origin, destination } = forecast;
  const p = samples[index];
  const ratio = (index / (samples.length - 1)) * 100;
  const peak = LABELS[p.category];
  let detail = "This part of the route has insufficient weather data.";
  if (p.method === "ti1")
    detail = `Wind shear ${p.shear?.toFixed(1)} m/s per km · Ellrod index ${p.ti1?.toFixed(1)}`;
  if (p.method === "cape")
    detail = `Surface CAPE ${p.cape?.toLocaleString("en-GB")} J/kg · climb/descent indicator`;
  if (p.method === "horizon")
    detail = "This section falls beyond the 36-hour forecast window.";
  if (p.method === "outside")
    detail = "This section passes outside the European forecast area.";
  return (
    <section className="timeline card" aria-label="Route timeline">
      <div className="timeline-top">
        <div>
          <span className="section-icon">
            <Wind size={17} />
          </span>
          <h2>Along the route</h2>
        </div>
        <span>{samples.length} sample points</span>
      </div>
      <div className="timeline-layout">
        <div className="track-area">
          <div className="track-captions">
            <b>{origin.code}</b>
            <b>{destination.code}</b>
          </div>
          <div className="track">
            <div className="bands" aria-hidden="true">
              {samples.slice(0, -1).map((s, i) => (
                <span key={i} style={{ background: COLORS[s.category] }} />
              ))}
            </div>
            <div
              className="thumb"
              style={{ left: ratio + "%" }}
              aria-hidden="true"
            />
            <input
              type="range"
              aria-label="Point along the route"
              aria-valuetext={`${Math.round(p.elapsedMinutes)} minutes, ${peak}`}
              min="0"
              max={samples.length - 1}
              value={index}
              onChange={(e) => onSelect(Number(e.target.value))}
            />
          </div>
          <div className="track-times">
            <span>{clock(forecast.departure)} UTC</span>
            <span>{clock(samples.at(-1)!.at)} UTC</span>
          </div>
          <p className="timeline-hint">
            Scrub the timeline or select a section on the map.
          </p>
        </div>
        <div className="sample-detail" aria-live="polite">
          <div className="detail-heading">
            <i style={{ background: COLORS[p.category] }} />
            <strong>{peak}</strong>
            <span>{p.phase}</span>
          </div>
          <div className="sample-facts">
            <span>
              <Clock3 size={14} />
              {duration(p.elapsedMinutes)} into flight
            </span>
            <span>
              <Mountain size={14} />
              {p.altitudeFt.toLocaleString("en-GB")} ft
            </span>
          </div>
          <p>{detail}</p>
        </div>
      </div>
    </section>
  );
}
