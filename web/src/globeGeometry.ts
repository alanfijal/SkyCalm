import type { FeatureCollection, LineString, Position } from "geojson";
import type { StyleSpecification } from "maplibre-gl";
import { COLORS, type Sample } from "./types";

export interface RouteLeg {
  path: [number, number][];
  color: [number, number, number];
}

export function routeLegs(samples: Sample[]): RouteLeg[] {
  return samples.slice(0, -1).map((sample, index) => {
    const next = samples[index + 1];
    const rgb = Number.parseInt(COLORS[sample.category].slice(1), 16);
    return {
      path: [
        [sample.lon, sample.lat],
        [next.lon, next.lat],
      ],
      color: [(rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255],
    };
  });
}

function graticule(): FeatureCollection<LineString> {
  const lines: Position[][] = [];
  for (let lat = -80; lat <= 80; lat += 10) {
    lines.push(Array.from({ length: 181 }, (_, i) => [-180 + i * 2, lat]));
  }
  for (let lon = -180; lon < 180; lon += 10) {
    lines.push(Array.from({ length: 83 }, (_, i) => [lon, -82 + i * 2]));
  }
  return {
    type: "FeatureCollection",
    features: lines.map((coordinates) => ({
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates },
    })),
  };
}

export function globeStyle(): StyleSpecification {
  return {
    version: 8,
    projection: { type: "globe" },
    sky: {
      "sky-color": "#101c29",
      "horizon-color": "#39556b",
      "fog-color": "#182c3b",
      "sky-horizon-blend": 0.06,
      "horizon-fog-blend": 0,
      "fog-ground-blend": 0,
      "atmosphere-blend": [
        "interpolate",
        ["linear"],
        ["zoom"],
        0,
        0.65,
        3,
        0.05,
        6,
        0,
      ],
    },
    sources: {
      countries: {
        type: "geojson",
        data: "/maps/land.geojson",
        attribution:
          '<a href="https://www.naturalearthdata.com/">Natural Earth</a>',
      },
      grid: { type: "geojson", data: graticule() },
      labels: { type: "geojson", data: "/maps/labels.json" },
    },
    layers: [
      {
        id: "ocean",
        type: "background",
        paint: { "background-color": "#122331" },
      },
      {
        id: "land",
        type: "fill",
        source: "countries",
        paint: {
          "fill-color": "#2b3e4a",
          "fill-outline-color": "#526570",
        },
      },
      {
        id: "borders",
        type: "line",
        source: "countries",
        paint: {
          "line-color": "#6c7b82",
          "line-opacity": 0.48,
          "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.5, 5, 1],
        },
      },
      {
        id: "graticule",
        type: "line",
        source: "grid",
        paint: {
          "line-color": "#a1b5bf",
          "line-opacity": 0.13,
          "line-width": 0.7,
          "line-dasharray": [2, 5],
        },
      },
      {
        id: "country-labels",
        type: "symbol",
        source: "labels",
        filter: ["any", ["<=", ["get", "rank"], 5], [">=", ["zoom"], 5]],
        layout: {
          "symbol-sort-key": ["get", "rank"],
          "text-field": ["upcase", ["get", "name"]],
          "text-font": ["Arial"],
          "text-size": [
            "interpolate",
            ["linear"],
            ["zoom"],
            1,
            8.5,
            4,
            11,
            6,
            13,
          ],
          "text-letter-spacing": 0.1,
          "text-max-width": 10,
          "text-padding": 6,
        },
        paint: {
          "text-color": "#a9bac3",
          "text-opacity": 0.88,
          "text-halo-color": "#263845",
          "text-halo-width": 1.1,
        },
      },
    ],
  };
}
