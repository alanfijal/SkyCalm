"""Passenger copy shared with the browser and Web Push sender."""

import json
from pathlib import Path

from services.forecast.schema import CATEGORIES

GUIDE = json.loads(
    (Path(__file__).resolve().parents[1] / "delivery" / "turbulence.json").read_text()
)


def alert_level(notice: dict, prefs: dict) -> str | None:
    peak = notice.get("peak")
    return peak if prefs.get("explainAlerts") is True and peak in CATEGORIES else None


def email_body(notice: dict, prefs: dict, inbox_url: str) -> str:
    prefix = "Test update." if notice["kind"].startswith("test-") else "Flight update."
    level = alert_level(notice, prefs)
    paragraphs = [prefix]
    if level:
        item = GUIDE["levels"][level]
        heading = "Smooth air" if level == "smooth" else f"{item['label']} turbulence"
        paragraphs.append(f"{heading} forecast. {item['summary']} {item['detail']}")
    paragraphs.extend([GUIDE["seatbelt"], f"Open your SkyCalm inbox.\n{inbox_url}".strip()])
    if level:
        paragraphs.append("FAA turbulence reporting guide\n" + GUIDE["source"])
    return "\n\n".join(paragraphs)
