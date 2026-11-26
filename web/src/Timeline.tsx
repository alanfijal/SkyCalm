import { Clock3, Mountain, Wind } from "lucide-react";
import { useRef } from "react";
import {
  guide,
  knownLevel,
  LevelButton,
  LevelText,
  useCabinGuide,
} from "./CabinGuide";
import { categoryColor } from "./theme";
import { clock, duration } from "./types";
import type { Forecast } from "./types";
import type { WeatherItem } from "./observations";

export default function Timeline({
  forecast,
  index,
  onSelect,
  observations,
  playing = false,
}: {
  forecast: Forecast;
  index: number;
  onSelect: (i: number) => void;
  observations: WeatherItem[] | null;
  playing?: boolean;
}) {
  const { samples, origin, destination } = forecast;
  const explain = useCabinGuide();
  const press = useRef<{ x: number; y: number } | null>(null);
  const p = samples[index];
  const ratio = (index / (samples.length - 1)) * 100;
  const peak = guide.levels[p.category].label;
  let detail = "This part of the route has insufficient weather data.";
  if (p.method === "ti1")
    detail = `Wind shear ${p.shear?.toFixed(1)} m/s per km · Ellrod index ${p.ti1?.toFixed(1)}`;
  if (p.method === "cape")
    detail = `Surface CAPE ${p.cape?.toLocaleString("en-GB")} J/kg · climb/descent indicator`;
  if (p.method === "lightgbm") {
    detail = `Model v${forecast.modelVersion} · ${Math.round((p.probability ?? 0) * 100)}% estimated probability of ${p.category}.`;
    if (p.driver)
      detail += ` The strongest contributing factor was ${p.driver}.`;
  }
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
      {forecast.briefing && (
        <p className="route-briefing">
          <LevelText text={forecast.briefing} />
        </p>
      )}
      <div className="timeline-layout">
        <div className="track-area">
          <div className="track-captions">
            <b>{origin.code}</b>
            <b>{destination.code}</b>
          </div>
          <div className="track">
            <div className="bands" aria-hidden="true">
              {samples.slice(0, -1).map((s, i) => (
                <span
                  key={i}
                  style={{ background: categoryColor(s.category) }}
                />
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
              onPointerDown={(e) => {
                press.current = { x: e.clientX, y: e.clientY };
              }}
              onPointerCancel={() => {
                press.current = null;
              }}
              onPointerUp={(e) => {
                const start = press.current;
                press.current = null;
                if (
                  !start ||
                  Math.hypot(e.clientX - start.x, e.clientY - start.y) > 5
                )
                  return;
                const bounds = e.currentTarget.getBoundingClientRect();
                const band = Math.max(
                  0,
                  Math.min(
                    samples.length - 1,
                    Math.floor(
                      ((e.clientX - bounds.left) / bounds.width) *
                        (samples.length - 1),
                    ),
                  ),
                );
                onSelect(band);
                explain(samples[band].category, e.currentTarget, {
                  x: e.clientX,
                  y: e.clientY,
                });
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  explain(p.category, e.currentTarget);
                }
              }}
            />
          </div>
          <div className="track-times">
            <span>{clock(forecast.departure)} UTC</span>
            <span>{clock(samples.at(-1)!.at)} UTC</span>
          </div>
          <p className="timeline-hint">
            Drag to explore. Select a section or press Enter on the timeline to
            see how it may feel.
          </p>
        </div>
        <div className="sample-detail" aria-live={playing ? "off" : "polite"}>
          <div className="detail-heading">
            <LevelButton level={p.category} marker>
              <strong>{peak}</strong>
              <small className="level-question">
                What does this feel like?
              </small>
            </LevelButton>
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
          <p>
            <LevelText text={detail} />
          </p>
          {observations && (
            <div className="segment-weather">
              <b>Nearby observations</b>
              {observations.length ? (
                <ul>
                  {observations.slice(0, 4).map((item) => (
                    <li key={item.id}>
                      {item.kind === "sigmet" ? "SIGMET " : ""}
                      {item.source} ·{" "}
                      <LevelButton
                        level={
                          knownLevel(item.intensity)
                            ? item.intensity
                            : "unreported"
                        }
                      />{" "}
                      · {clock(item.from)} UTC
                    </li>
                  ))}
                </ul>
              ) : (
                <p>
                  No matching weather reports or advisories for this section.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
