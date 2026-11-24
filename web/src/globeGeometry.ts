import type { FeatureCollection, LineString, Position } from "geojson";
import type {
  Map as Globe,
  SkySpecification,
  StyleSpecification,
} from "maplibre-gl";
import { categoryTokens } from "./theme";
import type { Category, Sample } from "./types";

type RGB = [number, number, number];

function rgb(hex: string): RGB {
  const digits = hex.slice(1);
  const full =
    digits.length === 3 ? [...digits].map((c) => c + c).join("") : digits;
  const value = Number.parseInt(full, 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

export function globePalette() {
  // MapLibre and deck.gl draw to a canvas, so they need resolved CSS colours.
  const style = getComputedStyle(document.documentElement);
  const read = (token: string) => style.getPropertyValue(token).trim();
  const route = Object.fromEntries(
    Object.entries(categoryTokens).map(([key, token]) => [
      key,
      rgb(read(token)),
    ]),
  ) as Record<Category, RGB>;
  return {
    sky: read("--bg"),
    water: read("--map-water"),
    land: read("--map-land"),
    coast: read("--map-coast"),
    label: read("--map-label"),
    horizon: read("--map-horizon"),
    casing: rgb(read("--map-casing")),
    route,
  };
}

type Palette = ReturnType<typeof globePalette>;

export interface RouteLeg {
  path: [number, number][];
  color: RGB;
}

export function routeLegs(
  samples: Sample[],
  colors: Record<Category, RGB>,
): RouteLeg[] {
  return samples.slice(0, -1).map((sample, index) => {
    const next = samples[index + 1];
    return {
      path: [
        [sample.lon, sample.lat],
        [next.lon, next.lat],
      ],
      color: colors[sample.category],
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

function sky(palette: Palette): SkySpecification {
  return {
    "sky-color": palette.sky,
    "horizon-color": palette.horizon,
    "fog-color": palette.water,
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
  };
}

type PaintProperty = Parameters<Globe["setPaintProperty"]>[1];

function paints(palette: Palette) {
  return {
    ocean: { "background-color": palette.water },
    land: { "fill-color": palette.land, "fill-outline-color": palette.coast },
    borders: { "line-color": palette.coast },
    graticule: { "line-color": palette.label },
    "country-labels": {
      "text-color": palette.label,
      "text-halo-color": palette.land,
    },
  } satisfies Record<string, Partial<Record<PaintProperty, string>>>;
}

export function recolorGlobe(map: Globe, palette: Palette) {
  map.setSky(sky(palette));
  for (const [layer, properties] of Object.entries(paints(palette))) {
    for (const [name, color] of Object.entries(properties)) {
      map.setPaintProperty(layer, name as PaintProperty, color);
    }
  }
}

export function globeStyle(palette: Palette): StyleSpecification {
  const paint = paints(palette);
  return {
    version: 8,
    projection: { type: "globe" },
    sky: sky(palette),
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
        paint: paint.ocean,
      },
      {
        id: "land",
        type: "fill",
        source: "countries",
        paint: paint.land,
      },
      {
        id: "borders",
        type: "line",
        source: "countries",
        paint: {
          ...paint.borders,
          "line-opacity": 0.65,
          "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.5, 5, 1],
        },
      },
      {
        id: "graticule",
        type: "line",
        source: "grid",
        paint: {
          ...paint.graticule,
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
          ...paint["country-labels"],
          "text-opacity": 0.88,
          "text-halo-width": 1.1,
        },
      },
    ],
  };
}
