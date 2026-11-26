import { useId } from "react";
import atlas from "./atlas.json";
import { categoryColor } from "./theme";
import { nightArea } from "./mapWeather";
import type { Category } from "./types";

export type PrintPoint = { lon: number; lat: number; category: Category };
export const exampleTrack = atlas.example as PrintPoint[];
export function RoutePrint({
  samples,
  from,
  to,
  selected,
  label,
  nightAt,
}: {
  samples: PrintPoint[];
  from: string;
  to: string;
  selected?: number;
  label: string;
  nightAt?: string;
}) {
  const id = useId();
  const points = samples.map((s) => [s.lon * 10, -s.lat * 15]);
  const xs = points.map((p) => p[0]),
    ys = points.map((p) => p[1]);
  const left = Math.min(...xs),
    top = Math.min(...ys),
    right = Math.max(...xs),
    bottom = Math.max(...ys);
  const height = Math.max(65, (bottom - top) * 1.32, (right - left) * 0.85);
  const width = height * 1.45,
    x = (left + right - width) / 2,
    y = (top + bottom - height) / 2;
  const line = height / 125,
    a = points[0],
    b = points[points.length - 1];
  const at = selected === undefined ? undefined : points[selected];
  const before = points[Math.max(0, (selected ?? 0) - 1)],
    after = points[Math.min(points.length - 1, (selected ?? 0) + 1)];
  const heading =
    (Math.atan2(after[0] - before[0], before[1] - after[1]) * 180) / Math.PI;
  return (
    <svg
      className="route-print"
      viewBox={[x, y, width, height].join(" ")}
      role="img"
      aria-label={label}
    >
      <defs>
        <pattern
          id={id}
          x="0"
          y="0"
          width="25"
          height="37.5"
          patternUnits="userSpaceOnUse"
        >
          <path
            d="M25 0H0V37.5"
            fill="none"
            stroke="var(--map-label)"
            strokeOpacity=".24"
            strokeWidth={line * 0.34}
          />
        </pattern>
      </defs>
      <rect
        x={x - width}
        y={y - height}
        width={width * 3}
        height={height * 3}
        fill="var(--map-water)"
      />
      <g
        fill="var(--map-land)"
        stroke="var(--map-coast)"
        strokeWidth={line * 0.4}
        fillRule="evenodd"
      >
        {atlas.land.map((d, i) => (
          <path key={i} d={d} />
        ))}
      </g>
      <rect
        x={x - width}
        y={y - height}
        width={width * 3}
        height={height * 3}
        fill={`url(#${id})`}
      />
      {nightAt && (
        <g fill="#081530" opacity=".22">
          {nightArea(nightAt).features.map((f, i) => (
            <polygon
              key={i}
              points={f.geometry.coordinates[0]
                .map(([x, y]) => [x * 10, -y * 15].join(","))
                .join(" ")}
            />
          ))}
        </g>
      )}
      <polyline
        fill="none"
        stroke="var(--map-casing)"
        strokeWidth={line * 3.1}
        points={points.map((p) => p.join(",")).join(" ")}
      />
      {points.slice(1).map((p, i) => (
        <line
          key={i}
          x1={points[i][0]}
          y1={points[i][1]}
          x2={p[0]}
          y2={p[1]}
          stroke={categoryColor(samples[i].category)}
          strokeLinecap="round"
          strokeWidth={line * 1.7}
        />
      ))}
      {[
        [a, from],
        [b, to],
      ].map(([p, code], i) => {
        const [px, py] = p as number[];
        const anchor = px > x + width * 0.69 ? "end" : "start";
        return (
          <g key={i}>
            <circle
              cx={px}
              cy={py}
              r={line * 2.3}
              fill="var(--text)"
              stroke="var(--map-water)"
              strokeWidth={line}
            />
            <text
              x={px + (anchor === "end" ? -1 : 1) * line * 4.8}
              y={py + line * 1.6}
              textAnchor={anchor}
              fontSize={line * 5.3}
              fontWeight="750"
              fill="var(--text)"
              stroke="var(--map-water)"
              strokeWidth={line * 1.4}
              paintOrder="stroke"
            >
              {code as string}
            </text>
          </g>
        );
      })}
      {at && (
        <path
          data-route-aircraft=""
          transform={[
            "translate(" + at.join(" ") + ")",
            "rotate(" + heading + ")",
            "scale(" + line + ")",
          ].join(" ")}
          d="M0 -5.5 1.1 -1 4.7 1.4 4.7 2.4 1 1.5 .7 4 2 5 0 4.5 -2 5 -.7 4 -1 1.5 -4.7 2.4 -4.7 1.4 -1.1 -1Z"
          fill="var(--text)"
          stroke="var(--map-water)"
          strokeWidth=".8"
          strokeLinejoin="round"
        />
      )}
    </svg>
  );
}
