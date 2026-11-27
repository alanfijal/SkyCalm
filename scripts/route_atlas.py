"""Build the small first-paint map from the bundled Natural Earth borders and classroom track."""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "web"


def simplify(points, tolerance=0.14):
    if len(points) <= 2:
        return points
    (ax, ay), (bx, by) = points[0], points[-1]
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy or 1
    worst, index = 0.0, 0
    for i, (x, y) in enumerate(points[1:-1], 1):
        t = min(1, max(0, ((x - ax) * dx + (y - ay) * dy) / length))
        distance = math.hypot(x - ax - t * dx, y - ay - t * dy)
        if distance > worst:
            worst, index = distance, i
    if worst <= tolerance:
        return [points[0], points[-1]]
    return simplify(points[: index + 1], tolerance)[:-1] + simplify(points[index:], tolerance)


def main():
    paths = []
    data = json.loads((ROOT / "public/maps/land.geojson").read_bytes())
    for feature in data["features"]:
        geom = feature["geometry"]
        polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for rings in polygons:
            if not any(-34 < x < 55 and 28 < y < 78 for x, y in rings[0]):
                continue
            chunks = []
            for ring in rings:
                simple = simplify(ring)
                if len(simple) > 3:
                    chunks.append(
                        "M" + " ".join(f"{x * 10:.0f},{-y * 15:.0f}" for x, y in simple) + "Z"
                    )
            if chunks:
                paths.append("".join(chunks))
    track = json.loads((ROOT / "public/data/recorded-flight/az1704-20261121.json").read_bytes())
    example = [{k: s[k] for k in ("lat", "lon", "category")} for s in track["samples"]]
    (ROOT / "src/atlas.json").write_text(
        json.dumps({"land": paths, "example": example}, separators=(",", ":")) + "\n"
    )


if __name__ == "__main__":
    main()
