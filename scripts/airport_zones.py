"""Generate the offline airport clocks from the checksum-pinned airportsdata wheel."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "e2ff963f4612a1bd56eb4dc059da35f2e9cfd6678a0812e4e611c12b8226abe0"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="airportsdata 20261126 wheel")
    wheel = parser.parse_args().wheel
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != DIGEST:
        parser.error("Unexpected airportsdata release")
    stations = json.loads((ROOT / "services/forecast/data/airports.json").read_text())
    with ZipFile(wheel) as archive:
        zones = {}
        for row in csv.DictReader(io.StringIO(archive.read("airportsdata/airports.csv").decode())):
            for code in (row["iata"], row["icao"]):
                if code and row["tz"]:
                    zones[code] = row["tz"]
        (ROOT / "web/public/maps/airportsdata-license.txt").write_bytes(
            archive.read("airportsdata-20261126.dist-info/licenses/LICENSE")
        )
    covered = {a["code"] for a in stations if 34 <= a["lat"] <= 72 and -25 <= a["lon"] <= 45}
    # Heliports and alternate identifiers omitted from airportsdata. Use the IANA
    # locality for these named sites in OurAirports (including Ceuta and east Greenland).
    zones.update(
        {
            "FCN": "Europe/Berlin",
            "FOA": "Europe/London",
            "GZM": "Europe/Malta",
            "JCU": "Africa/Ceuta",
            "KVO": "Europe/Belgrade",
            "LEAG": "Europe/Madrid",
            "MCM": "Europe/Monaco",
            "OBY": "America/Scoresbysund",
            "PZE": "Europe/London",
            "TQR": "Europe/Rome",
            "UGAM": "Asia/Tbilisi",
            "UGMS": "Asia/Tbilisi",
            "UGSA": "Asia/Tbilisi",
            "VRY": "Europe/Oslo",
        }
    )
    result = {c: zones[c] for c in sorted(covered & zones.keys())}
    (ROOT / "web/src/airportZones.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"{len(result)} of {len(covered)} covered airport clocks. Others use explicit UTC input.")


if __name__ == "__main__":
    main()
