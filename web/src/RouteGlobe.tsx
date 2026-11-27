import { useEffect, useRef, useState } from "react";
import { useGlobeWeather, advisoryHatch } from "./globeWeather";
import { useMedia } from "./useMedia";
import { useCabinGuide } from "./CabinGuide";
import { MapLibreOverlay } from "@deck.gl/maplibre";
import { PathLayer } from "@deck.gl/layers";
import { Crosshair, Minus, Plus } from "lucide-react";
import {
  LngLatBounds,
  Map as Globe,
  Marker,
  setWorkerUrl,
  type MapMouseEvent,
  type GeoJSONSource,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  globePalette,
  globeStyle,
  recolorGlobe,
  routeLegs,
  type RouteLeg,
} from "./globeGeometry";
import type { Theme } from "./theme";
import type { WeatherItem } from "./observations";
import { type Airport, type Sample } from "./types";
import "./globe.css";

setWorkerUrl(workerUrl);

interface Props {
  theme: Theme;
  samples: Sample[];
  origin: Airport;
  destination: Airport;
  selected: number;
  observations: WeatherItem[];
  showNight: boolean;
  windFrame?: string;
  onSelect: (index: number) => void;
}

function fitRoute(map: Globe, samples: Sample[]) {
  if (!samples.length) return;
  const bounds = new LngLatBounds();
  for (const p of samples) bounds.extend([p.lon, p.lat]);
  const { clientWidth: w, clientHeight: h } = map.getContainer();
  if (!w || !h) return;
  map.fitBounds(bounds, {
    padding: {
      left: Math.min(76, Math.max(30, Math.round(w * 0.08))),
      right: Math.min(94, Math.max(64, Math.round(w * 0.1))),
      top: Math.min(72, Math.max(44, Math.round(h * 0.15))),
      bottom: Math.min(72, Math.max(48, Math.round(h * 0.16))),
    },
    maxZoom: map.getMaxZoom(),
    pitch: 0,
    bearing: 0,
    duration: 0,
  });
}

function airportMarker(
  map: Globe,
  airport: Airport,
  end: "origin" | "destination",
  select: () => void,
): Marker {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `globe-airport globe-airport--${end}`;
  button.setAttribute(
    "aria-label",
    `${airport.code} · ${airport.name} · select on the route`,
  );
  const tag = document.createElement("span");
  tag.textContent = airport.code;
  button.append(tag);
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    select();
  });
  return new Marker({
    element: button,
    subpixelPositioning: true,
    opacityWhenCovered: 0,
  })
    .setLngLat([airport.lon, airport.lat])
    .addTo(map);
}

export default function RouteGlobe({
  theme,
  samples,
  origin,
  destination,
  selected,
  observations,
  showNight,
  windFrame,
  onSelect,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const explain = useCabinGuide();
  const select = useRef(onSelect);
  const route = useRef(samples);
  const plane = useRef<Marker | null>(null);
  const overlay = useRef<MapLibreOverlay | null>(null);
  const drawnTheme = useRef(theme);
  const [map, setMap] = useState<Globe | null>(null);
  const [failed, setFailed] = useState(false);
  const current = samples[selected];
  const reducedMotion = useMedia("(prefers-reduced-motion: reduce)");
  const drawnRoute = useRef<Sample[] | null>(null);
  useGlobeWeather(map, current.at, showNight, windFrame, theme, reducedMotion);
  useEffect(() => {
    select.current = onSelect;
  }, [onSelect]);
  useEffect(() => {
    route.current = samples;
  }, [samples]);

  useEffect(() => {
    const node = container.current;
    if (!node) return;
    let instance: Globe;
    try {
      instance = new Globe({
        container: node,
        style: globeStyle(globePalette()),
        center: [10, 50],
        zoom: 2.4,
        minZoom: 0.5,
        maxZoom: 7,
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        fadeDuration: 0,
        pixelRatio: Math.min(window.devicePixelRatio, 1.5),
        attributionControl: { compact: true },
        canvasContextAttributes: { antialias: true },
      });
    } catch {
      setFailed(true);
      return;
    }
    instance.touchZoomRotate.disableRotation();
    instance
      .getCanvas()
      .setAttribute(
        "aria-label",
        "Globe of the flight route. Use arrow keys to pan.",
      );
    instance.on("load", () => {
      const ribbons = new MapLibreOverlay({ interleaved: true, layers: [] });
      instance.addControl(ribbons);
      overlay.current = ribbons;
      setMap(instance);
    });
    const observer = new ResizeObserver(() => {
      instance.resize();
      if (instance.isStyleLoaded()) fitRoute(instance, route.current);
    });
    observer.observe(node);
    return () => {
      observer.disconnect();
      overlay.current = null;
      instance.remove();
    };
  }, []);

  useEffect(() => {
    if (!map) return;
    if (!map.getSource("observations")) {
      if (!observations.length) return;
      map.addSource("observations", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "weather-areas",
        type: "fill",
        source: "observations",
        filter: ["==", ["get", "kind"], "sigmet"],
        paint: { "fill-opacity": 0.16 },
      });
      map.addLayer({
        id: "weather-hatch",
        type: "fill",
        source: "observations",
        filter: ["==", ["get", "kind"], "sigmet"],
        paint: { "fill-opacity": 0.5 },
      });
      map.addLayer({
        id: "weather-lines",
        type: "line",
        source: "observations",
        filter: ["==", ["get", "kind"], "sigmet"],
        paint: { "line-width": 1.8, "line-dasharray": [3, 2] },
      });
      map.addLayer({
        id: "weather-points",
        type: "circle",
        source: "observations",
        filter: ["==", ["get", "kind"], "report"],
        paint: { "circle-radius": 4.5, "circle-stroke-width": 1.5 },
      });
    }
    const style = getComputedStyle(document.documentElement);
    const color = (token: string) => style.getPropertyValue(token).trim();
    map.setPaintProperty(
      "weather-hatch",
      "fill-pattern",
      advisoryHatch(map, theme),
    );
    map.setPaintProperty("weather-areas", "fill-color", color("--accent"));
    map.setPaintProperty("weather-lines", "line-color", color("--accent"));
    map.setPaintProperty("weather-points", "circle-color", color("--replay"));
    map.setPaintProperty(
      "weather-points",
      "circle-stroke-color",
      color("--surface"),
    );
    map.getSource<GeoJSONSource>("observations")?.setData({
      type: "FeatureCollection",
      features: observations.map((item) => ({
        type: "Feature",
        id: item.id,
        geometry: item.geometry,
        properties: { kind: item.kind },
      })),
    });
  }, [map, observations, theme]);

  useEffect(() => {
    const ribbons = overlay.current;
    if (!map || !ribbons) return;
    const palette = globePalette();
    if (drawnTheme.current !== theme) {
      recolorGlobe(map, palette);
      drawnTheme.current = theme;
    }
    const legs = routeLegs(samples, palette.route);
    const line = new PathLayer<RouteLeg>({
      id: "forecast-route",
      data: legs,
      getPath: (leg) => leg.path,
      getColor: (leg) => leg.color,
      widthUnits: "pixels",
      getWidth: 4,
      capRounded: true,
      jointRounded: true,
      pickable: true,
    });
    const paint = (count: number) => {
      const visible =
        count === legs.length
          ? line
          : line.clone({ data: legs.slice(0, count) });
      ribbons.setProps({
        layers: [
          visible.clone({
            id: "forecast-halo",
            getWidth: 6.5,
            getColor: palette.casing,
            opacity: 0.48,
            parameters: { depthWriteEnabled: false },
            pickable: false,
          }),
          visible,
        ],
      });
    };
    const animate =
      !reducedMotion && !document.hidden && drawnRoute.current !== samples;
    drawnRoute.current = samples;
    if (!animate) {
      paint(legs.length);
      return;
    }
    const start = performance.now();
    let request = 0;
    const draw = (now: number) => {
      const progress = Math.min(1, Math.max(0, (now - start) / 620));
      paint(Math.ceil(legs.length * progress));
      if (progress < 1) request = requestAnimationFrame(draw);
    };
    draw(start);
    return () => cancelAnimationFrame(request);
  }, [map, samples, theme, reducedMotion]);

  useEffect(() => {
    const ribbons = overlay.current;
    if (!map || !ribbons || !samples.length) return;
    const from = airportMarker(map, origin, "origin", () => select.current(0));
    const to = airportMarker(map, destination, "destination", () =>
      select.current(samples.length - 1),
    );
    const aircraft = document.createElement("div");
    aircraft.className = "globe-plane";
    aircraft.setAttribute("aria-hidden", "true");
    const marker = new Marker({
      element: aircraft,
      subpixelPositioning: true,
      opacityWhenCovered: 0,
    })
      .setLngLat([origin.lon, origin.lat])
      .addTo(map);
    plane.current = marker;
    fitRoute(map, samples);

    function pick(event: MapMouseEvent) {
      // Evaluate in screen pixels so the hit area is constant at every zoom.
      const { x, y } = event.point;
      const hit = ribbons?.pickObject({
        x,
        y,
        radius: 8,
        layerIds: ["forecast-route"],
      });
      if (!hit?.picked) return;
      // Each painted leg uses its starting sample's category.
      select.current(hit.index);
      explain(samples[hit.index].category, event.target.getCanvas(), {
        x: event.originalEvent.clientX,
        y: event.originalEvent.clientY,
      });
    }

    map.on("click", pick);
    return () => {
      map.off("click", pick);
      from.remove();
      to.remove();
      marker.remove();
      plane.current = null;
    };
  }, [map, samples, origin, destination, explain]);

  useEffect(() => {
    const marker = plane.current;
    if (!map || !current || !marker) return;
    const ahead = samples[Math.min(selected + 1, samples.length - 1)];
    const behind = samples[Math.max(0, selected - 1)];
    marker.setLngLat([current.lon, current.lat]);
    function orient() {
      if (!map || !marker) return;
      const a = map.project([behind.lon, behind.lat]);
      const b = map.project([ahead.lon, ahead.lat]);
      marker.setRotation((Math.atan2(b.x - a.x, a.y - b.y) * 180) / Math.PI);
    }
    orient();
    map.on("move", orient);
    return () => {
      map.off("move", orient);
    };
  }, [map, current, selected, samples, origin, destination]);

  return (
    <div
      className="route-globe"
      role="region"
      aria-label={`Route map from ${origin.code} to ${destination.code}`}
    >
      <div ref={container} className="route-globe__canvas" />
      {failed ? (
        <div className="route-globe__fallback" role="status">
          <strong>
            {origin.code} → {destination.code}
          </strong>
          <span>
            The 3D map is unavailable in this browser. Use the timeline to
            explore your route.
          </span>
        </div>
      ) : (
        <div
          className="route-globe__controls"
          role="group"
          aria-label="Map controls"
        >
          <button
            type="button"
            disabled={!map}
            onClick={() => map?.zoomIn({ duration: 0 })}
            aria-label="Zoom in"
            title="Zoom in"
          >
            <Plus size={16} />
          </button>
          <button
            type="button"
            disabled={!map}
            onClick={() => map?.zoomOut({ duration: 0 })}
            aria-label="Zoom out"
            title="Zoom out"
          >
            <Minus size={16} />
          </button>
          <button
            type="button"
            disabled={!map}
            onClick={() => map && fitRoute(map, samples)}
            aria-label="Fit route to map"
            title="Fit route to map"
          >
            <Crosshair size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
