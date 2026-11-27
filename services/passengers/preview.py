"""Generate messaging previews from the explicitly shared route, UTC date and peak."""

import base64
from datetime import UTC, datetime
from html import escape
from io import BytesIO
from urllib.parse import urlsplit

from services.passengers.sharing import granted_flight, unavailable

COLORS = {"smooth": "#7DD3C0", "light": "#F4D35E", "moderate": "#F4A259", "severe": "#E4572E"}


def card_png(origin: str, destination: str, date: str, peak: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1200, 630), "#0B1220")
    draw = ImageDraw.Draw(image)

    def label(x, y, text, size, color):
        draw.text((x, y), text, font=ImageFont.load_default(size=size), fill=color)

    label(72, 55, "SkyCalm", 43, "#8AB4FF")
    draw.line((72, 142, 1128, 142), fill="#26324A", width=3)
    label(69, 184, origin, 105, "#E8EEF7")
    draw.line((395, 258, 625, 258), fill="#8AB4FF", width=6)
    draw.polygon([(625, 245), (650, 258), (625, 271)], fill="#8AB4FF")
    label(722, 184, destination, 105, "#E8EEF7")
    label(72, 356, date + " UTC", 40, "#CFD9EA")
    draw.ellipse((74, 479, 101, 506), fill=COLORS.get(peak, "#9AA8BF"))
    label(123, 462, "Peak forecast: " + peak.capitalize(), 43, "#E8EEF7")
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def preview_response(store, ticket: str, image: bool, now: int, site: str, api: str) -> dict:
    flight, _ = granted_flight(store, ticket, now, "card-v1")
    if any(urlsplit(url).scheme != "https" or not urlsplit(url).hostname for url in (site, api)):
        raise unavailable()
    origin, dest = flight["origin"], flight["destination"]
    date = datetime.fromisoformat(flight["departure"]).astimezone(UTC).strftime("%d %b %Y")
    peak = (flight.get("assessment") or {}).get("peak", "unavailable")
    headers = {
        "cache-control": "private, no-store",
        "referrer-policy": "no-referrer",
        "x-content-type-options": "nosniff",
        "x-robots-tag": "noindex, nofollow, noarchive",
    }
    if image:
        return {
            "statusCode": 200,
            "headers": {**headers, "content-type": "image/png"},
            "isBase64Encoded": True,
            "body": base64.b64encode(card_png(origin, dest, date, peak)).decode(),
        }
    title = escape(f"{origin} → {dest} · SkyCalm", quote=True)
    description = escape(f"{date} UTC · Peak forecast: {peak.capitalize()}", quote=True)
    url = escape(f"{api.rstrip('/')}/family/{ticket}", quote=True)
    script = escape(site.rstrip("/") + "/family-open.js", quote=True)
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<meta property="og:type" content="website"><meta property="og:title" content="{title}">
<meta property="og:description" content="{description}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{url}.png"><meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630"><meta property="og:image:alt" content="{title}. {description}">
<meta name="twitter:card" content="summary_large_image"><script defer src="{script}"></script></head>
<body><main><h1>{title}</h1><p>{description}</p></main></body></html>"""
    return {
        "statusCode": 200,
        "headers": {
            **headers,
            "content-type": "text/html; charset=utf-8",
            "content-security-policy": f"default-src 'none'; script-src {site.rstrip('/')}; base-uri 'none'; frame-ancestors 'none'",
        },
        "body": body,
    }
