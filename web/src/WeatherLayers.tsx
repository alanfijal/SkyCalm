import { Layers3 } from "lucide-react";
import "./weather.css";
import { clock, dateLabel } from "./types";
import type { LayerChoice, WeatherSnapshot } from "./observations";

interface Props {
  choice: LayerChoice;
  onChange: (c: LayerChoice) => void;
  data: WeatherSnapshot | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
}
export default function WeatherLayers({
  choice,
  onChange,
  data,
  loading,
  error,
  onRetry,
}: Props) {
  const active = choice.report || choice.sigmet;
  return (
    <details className="weather-layers">
      <summary>
        <Layers3 size={16} /> Map layers
      </summary>
      <div className="weather-layers__panel">
        <label>
          <input
            type="checkbox"
            checked={choice.sigmet}
            onChange={(e) => onChange({ ...choice, sigmet: e.target.checked })}
          />
          <i className="sigmet-symbol" /> Turbulence advisories
        </label>
        <label>
          <input
            type="checkbox"
            checked={choice.report}
            onChange={(e) => onChange({ ...choice, report: e.target.checked })}
          />
          <i className="report-symbol" /> Aircraft weather reports
        </label>
        {active && (
          <div className="layer-status" role="status">
            {loading ? (
              "Loading observations…"
            ) : error ? (
              <>
                {error}{" "}
                <button type="button" onClick={onRetry}>
                  Retry
                </button>
              </>
            ) : data ? (
              <>
                <strong>
                  {data.mode === "replay"
                    ? "Archived observations"
                    : data.stale
                      ? "Last observation update"
                      : "Observations updated"}
                </strong>
                <span>
                  {dateLabel(data.asOf)} · {clock(data.asOf)} UTC
                </span>
                <span>
                  {data.items.filter((r) => r.kind === "sigmet").length}{" "}
                  advisories ·{" "}
                  {
                    data.items.filter(
                      (r) =>
                        r.kind === "report" && r.intensity !== "unreported",
                    ).length
                  }{" "}
                  reports with turbulence information
                </span>
                {data.limited && (
                  <span>The source capped the report list.</span>
                )}
                <span>{data.source} · issuing weather offices</span>
              </>
            ) : null}
          </div>
        )}
      </div>
    </details>
  );
}
