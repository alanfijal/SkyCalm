import {
  lazy,
  Suspense,
  useEffect,
  useState,
  type ComponentProps,
} from "react";
import { Globe2 } from "lucide-react";
import WeatherLayers from "./WeatherLayers";
import { RoutePrint } from "./RoutePrint";
import { windLead } from "./mapWeather";
import type { Theme } from "./theme";
import { clock, fetchWithRetry, type Forecast } from "./types";
import type { WeatherItem } from "./observations";
import { Skeleton } from "./PageSkeleton";
import "./mapPanel.css";

const Globe = lazy(() => import("./RouteGlobe"));
const archiveRuns = new Set(["gfs-20261121-06", "gfs-20261124-12"]);
const noWeather = {
  choice: { sigmet: false, report: false },
  onChange: () => {},
  data: null,
  loading: false,
  error: "",
  onRetry: () => {},
};
export function ForecastMap({
  forecast,
  theme,
  selected,
  onSelect,
  observations,
  weather,
}: {
  forecast: Forecast;
  theme: Theme;
  selected: number;
  onSelect: (i: number) => void;
  observations: WeatherItem[];
  weather?: ComponentProps<typeof WeatherLayers>;
}) {
  const [interactive, setInteractive] = useState(
    () => matchMedia("(min-width:48rem)").matches,
  );
  const [night, setNight] = useState(true),
    [wind, setWind] = useState(false);
  const [archive, setArchive] = useState<{
    run: string;
    frames?: string[];
    failed?: boolean;
  }>();
  const run = forecast.run.runId,
    archived = archiveRuns.has(run);
  const lead = windLead(forecast.run.issued, forecast.samples[selected].at);
  const available = Boolean(forecast.wind250 || archived);
  useEffect(() => {
    if (!wind || forecast.wind250 || !archived) return;
    const c = new AbortController();
    fetchWithRetry("/data/wind/" + run + ".json", 8000, c.signal)
      .then(async (r) => {
        if (!r.ok) throw Error("wind");
        return (await r.json()) as string[];
      })
      .then((frames) => {
        if (!c.signal.aborted) setArchive({ run, frames });
      })
      .catch(() => {
        if (!c.signal.aborted) setArchive({ run, failed: true });
      });
    return () => c.abort();
  }, [wind, run, archived, forecast.wind250]);
  const frames =
    forecast.wind250 ?? (archive?.run === run ? archive.frames : undefined);
  const frame = wind && lead >= 0 ? frames?.[lead] : undefined;
  return (
    <div className="map-viewport">
      <WeatherLayers
        {...(weather ?? noWeather)}
        hideObservations={!weather}
        onChange={(choice) => {
          setInteractive(true);
          weather?.onChange(choice);
        }}
      >
        <label>
          <input
            type="checkbox"
            checked={night}
            onChange={(e) => setNight(e.target.checked)}
          />
          Day and night
        </label>
        <label>
          <input
            type="checkbox"
            checked={available && wind}
            disabled={!available}
            onChange={(e) => {
              setWind(e.target.checked);
              if (e.target.checked) setInteractive(true);
            }}
          />
          Cruise winds · 250 hPa
        </label>
        {!available && <small>Wind vectors unavailable for this run.</small>}
        {wind && available && (
          <small role="status">
            {lead < 0
              ? "Outside the wind forecast window."
              : frame
                ? "GFS winds · " +
                  clock(
                    new Date(
                      Date.parse(forecast.run.issued) + lead * 10800000,
                    ).toISOString(),
                  ) +
                  " UTC · stronger winds draw longer lines"
                : archive?.run === run && archive.failed
                  ? "Wind layer unavailable. Toggle to retry."
                  : "Loading wind vectors…"}
          </small>
        )}
      </WeatherLayers>
      {interactive ? (
        <Suspense
          fallback={
            <div className="map-poster">
              <Skeleton label="Loading the interactive globe…" />
            </div>
          }
        >
          <Globe
            theme={theme}
            samples={forecast.samples}
            origin={forecast.origin}
            destination={forecast.destination}
            selected={selected}
            observations={observations}
            onSelect={onSelect}
            showNight={night}
            windFrame={frame}
          />
        </Suspense>
      ) : (
        <div
          className="map-poster"
          role="region"
          aria-label={`Route map from ${forecast.origin.code} to ${forecast.destination.code}`}
        >
          <RoutePrint
            samples={forecast.samples}
            from={forecast.origin.code}
            to={forecast.destination.code}
            selected={selected}
            nightAt={night ? forecast.samples[selected].at : undefined}
            label="Route overview coloured by forecast intensity"
          />
          <button
            type="button"
            className="activate-globe"
            onClick={() => setInteractive(true)}
          >
            <Globe2 size={17} /> Explore globe
          </button>
        </div>
      )}
    </div>
  );
}
