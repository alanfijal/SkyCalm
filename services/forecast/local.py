"""Serve built public assets and the shared forecast API on loopback."""

import argparse
import gzip
import json
import logging
import mimetypes
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from services.flights.local import LocalLedger, local_lookup
from services.forecast.api import RequestError
from services.forecast.http import response
from services.forecast.storage import REPLAY_ROOT, LocalStore

ROOT = Path(__file__).resolve().parents[2]


def accepts_gzip(header: str) -> bool:
    for item in header.lower().split(","):
        encoding, _, parameters = item.strip().partition(";")
        if encoding.strip() == "gzip":
            try:
                return float(parameters.strip().removeprefix("q=") or "1") > 0
            except ValueError:
                return False
    return False


def make_handler(store: LocalStore, public: Path, lookup_dir: Path = ROOT / ".local"):
    ledger = LocalLedger(lookup_dir)

    class Handler(BaseHTTPRequestHandler):
        def send(self, status: int, headers: dict, body: bytes) -> None:
            kind = next((v for k, v in headers.items() if k.lower() == "content-type"), "")
            compressible = kind.startswith("text/") or any(
                t in kind for t in ("javascript", "json", "svg+xml")
            )
            if self.command == "GET" and compressible and len(body) >= 1024:
                headers = {**headers, "Vary": "Accept-Encoding"}
                if accepts_gzip(self.headers.get("Accept-Encoding", "")):
                    body = gzip.compress(body, compresslevel=5, mtime=0)
                    headers["Content-Encoding"] = "gzip"
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            headers = {"Content-Type": "application/json", "Cache-Control": "no-store"}
            port = self.server.server_port
            host = self.headers.get("Host")
            try:
                if self.path != "/api/me/flight-lookup":
                    raise RequestError("not_found", "Unknown endpoint.", 404)
                if host not in (f"127.0.0.1:{port}", f"localhost:{port}") or self.headers.get(
                    "Origin"
                ) not in (None, "http://" + host):
                    raise RequestError("origin", "Use the local SkyCalm site.", 403)
                if self.headers.get_content_type() != "application/json":
                    raise RequestError("content_type", "Send JSON.", 415)
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 512:
                    raise RequestError("size", "Invalid request size.", 400)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError
                result = local_lookup(body, lookup_dir, ledger)
                status = 200
            except RequestError as exc:
                status, result = exc.status, {"error": exc.code, "message": str(exc)}
            except (ValueError, UnicodeError):
                status, result = (
                    400,
                    {
                        "error": "invalid_body",
                        "message": "Enter a flight number and departure date.",
                    },
                )
            except Exception:
                status, result = (
                    503,
                    {
                        "error": "unavailable",
                        "message": "Flight lookup is temporarily unavailable.",
                    },
                )
            self.send(status, headers, json.dumps(result).encode())

        def do_GET(self) -> None:
            request = urlsplit(self.path)
            if request.path.startswith("/api/"):
                result = response("GET", request.path, request.query, store, uuid.uuid4().hex)
                self.send(result["statusCode"], result["headers"], result["body"].encode())
                return
            asset = (
                "index.html"
                if request.path
                in (
                    "/",
                    "/flights",
                    "/forecast",
                    "/shared",
                    "/demo",
                    "/health",
                    "/history",
                    "/replay",
                    "/recordings",
                )
                else unquote(request.path).lstrip("/")
            )
            local = (public / asset).resolve()
            if not local.is_relative_to(public) or not local.is_file():
                self.send(404, {"Content-Type": "text/plain"}, b"Page unavailable.")
                return
            self.send(
                200,
                {
                    "Content-Type": mimetypes.guess_type(local.name)[0]
                    or "application/octet-stream",
                    "X-Content-Type-Options": "nosniff",
                },
                local.read_bytes(),
            )

        def log_message(self, fmt: str, *args) -> None:
            pass  # Avoid logging personal itinerary query strings.

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=4173, type=int)
    parser.add_argument("--data", default=ROOT / ".local/weather", type=Path)
    parser.add_argument("--lookup-dir", default=ROOT / ".local", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    handler = make_handler(
        LocalStore(args.data, REPLAY_ROOT), (ROOT / "web/dist").resolve(), args.lookup_dir
    )
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"SkyCalm is available at http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
