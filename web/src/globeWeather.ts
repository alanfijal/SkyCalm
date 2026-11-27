import { useEffect } from "react";
import type { GeoJSONSource, Map as Globe } from "maplibre-gl";
import { nightArea, windLines } from "./mapWeather";
import type { Theme } from "./theme";

export function advisoryHatch(map: Globe, theme: Theme) {
  const id = "advisory-hatch-" + theme;
  if (map.hasImage(id)) return id;
  const data = new Uint8Array(8 * 8 * 4);
  const rgb = theme === "dark" ? [220, 232, 255] : [25, 55, 103];
  for (let y = 0; y < 8; y++)
    for (let x = 0; x < 8; x++)
      if ((x + y) % 8 < 2) data.set([...rgb, 220], 4 * (y * 8 + x));
  map.addImage(id, { width: 8, height: 8, data });
  return id;
}

export function useGlobeWeather(
  map: Globe | null,
  at: string,
  night: boolean,
  wind: string | undefined,
  theme: Theme,
  reduced: boolean,
) {
  useEffect(() => {
    if (!map) return;
    if (!map.getSource("night")) {
      if (!night) return;
      map.addSource("night", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer(
        {
          id: "night",
          type: "fill",
          source: "night",
          paint: { "fill-color": "#07152e", "fill-antialias": false },
        },
        "country-labels",
      );
    }
    map.setPaintProperty(
      "night",
      "fill-opacity",
      theme === "dark" ? 0.48 : 0.2,
    );
    map.setLayoutProperty("night", "visibility", night ? "visible" : "none");
    if (night) map.getSource<GeoJSONSource>("night")?.setData(nightArea(at));
  }, [map, night, at, theme]);

  useEffect(() => {
    if (!map) return;
    if (!map.getSource("cruise-wind")) {
      if (!wind) return;
      map.addSource("cruise-wind", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer(
        {
          id: "wind-trails",
          type: "line",
          source: "cruise-wind",
          paint: { "line-width": 1.5, "line-opacity": 0.32 },
        },
        "country-labels",
      );
      map.addLayer(
        {
          id: "wind-flow",
          type: "line",
          source: "cruise-wind",
          paint: {
            "line-width": 2,
            "line-dasharray": [1, 4],
            "line-opacity": 0.8,
          },
        },
        "country-labels",
      );
    }
    const color = getComputedStyle(document.documentElement)
      .getPropertyValue("--accent")
      .trim();
    for (const id of ["wind-trails", "wind-flow"]) {
      map.setLayoutProperty(id, "visibility", wind ? "visible" : "none");
      map.setPaintProperty(id, "line-color", color);
    }
    if (!wind) return;
    map.getSource<GeoJSONSource>("cruise-wind")?.setData(windLines(wind));
    const dashes = [
      [1, 4],
      [0, 1, 1, 3],
      [0, 2, 1, 2],
      [0, 3, 1, 1],
      [0, 4, 1, 0],
    ];
    let step = 0,
      timer = 0;
    const motion = () => {
      window.clearInterval(timer);
      if (!reduced && !document.hidden)
        timer = window.setInterval(() => {
          step = (step + 1) % dashes.length;
          map.setPaintProperty("wind-flow", "line-dasharray", dashes[step]);
        }, 160);
    };
    motion();
    document.addEventListener("visibilitychange", motion);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", motion);
    };
  }, [map, wind, theme, reduced]);
}
