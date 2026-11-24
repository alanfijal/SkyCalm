"""Serve the private classroom console on loopback only."""

import argparse
import hmac
import json
import os
import re
import secrets
import subprocess
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from services.pipeline.contract import REPLAYS
from services.pipeline.jobs import stamp
from services.pipeline.operator_backend import CloudOperator, LocalOperator, valid_id

PANEL = Path(__file__).with_name("panel")
AUDIT = Path(__file__).resolve().parents[2] / ".local/operator-actions.jsonl"


def handler_for(backend, token, audit):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type="application/json"):
            if content_type == "application/json":
                body = json.dumps(
                    body, default=lambda n: int(n) if isinstance(n, Decimal) else str(n)
                ).encode()
            self.send_response(status)
            for name, value in {
                "Content-Type": content_type,
                "Content-Length": str(len(body)),
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
                "X-Frame-Options": "DENY",
            }.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def trusted(self, post=False):
            host = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == host and (
                not post or self.headers.get("Origin") == "http://" + host
            )

        def allowed(self):
            return hmac.compare_digest(self.headers.get("X-SkyCalm-Token", ""), token)

        def do_GET(self):
            path = urlsplit(self.path).path
            if not self.trusted():
                return self.reply(403, {"error": "Use the loopback address printed at startup"})
            if path in ("/", "/demo", "/health"):
                body = (PANEL / "index.html").read_text().replace("{{token}}", token).encode()
                return self.reply(200, body, "text/html; charset=utf-8")
            if path in ("/panel.js", "/panel.css"):
                mime = "text/javascript" if path.endswith(".js") else "text/css"
                return self.reply(200, (PANEL / path[1:]).read_bytes(), mime)
            if not self.allowed():
                return self.reply(403, {"error": "Reload the operator console"})
            try:
                if path == "/api/session":
                    return self.reply(
                        200,
                        {
                            "mode": backend.mode,
                            "cloud": isinstance(backend, CloudOperator),
                            "runs": list(REPLAYS),
                        },
                    )
                if path == "/api/health":
                    return self.reply(200, backend.health())
                if path.startswith("/api/jobs/") and valid_id(path[10:]):
                    return self.reply(200, backend.status(path[10:]))
            except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
                return self.reply(503, {"error": str(exc)[:150]})
            self.reply(404, {"error": "Unknown operator route"})

        def do_POST(self):
            if not self.trusted(post=True) or not self.allowed():
                return self.reply(403, {"error": "Open the console on this device"})
            action = urlsplit(self.path).path
            if action not in ("/api/publish", "/api/discover", "/api/probe"):
                return self.reply(404, {"error": "Unknown action"})
            if self.headers.get_content_type() != "application/json":
                return self.reply(415, {"error": "Expected JSON"})
            request_id = None
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2048:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict) or not re.fullmatch(
                    r"[0-9a-f]{32}", str(data.get("requestId", ""))
                ):
                    raise ValueError("Invalid request ID")
                request_id = data["requestId"]
                self.audit(action, request_id, "requested")
                if action == "/api/publish":
                    result = backend.publish(data.get("run"), request_id)
                elif not isinstance(backend, CloudOperator):
                    raise ValueError("This action requires an AWS operator session")
                elif action == "/api/probe":
                    result = backend.probe(request_id)
                else:
                    result = backend.discover()
            except (ValueError, TypeError) as exc:
                return self.reply(400, {"error": str(exc)[:150]})
            except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
                return self.reply(503, {"error": str(exc)[:150]})
            self.audit(action, request_id, "accepted")
            self.reply(202, result)

        def audit(self, action, request_id, result):
            audit.parent.mkdir(parents=True, exist_ok=True)
            row = {
                "at": stamp(),
                "principal": backend.principal,
                "action": action,
                "requestId": request_id,
                "result": result,
            }
            fd = os.open(audit, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as log:
                log.write(json.dumps(row) + "\n")

        def log_message(self, *_args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aws", action="store_true")
    parser.add_argument("--account", default=os.environ.get("TF_VAR_account_id"))
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "default"))
    parser.add_argument("--port", type=int, default=4174)
    args = parser.parse_args()
    backend = CloudOperator(args.account, args.profile) if args.aws else LocalOperator()
    try:
        with ThreadingHTTPServer(
            ("127.0.0.1", args.port), handler_for(backend, secrets.token_urlsafe(32), AUDIT)
        ) as server:
            print(f"{backend.mode}: http://127.0.0.1:{server.server_port}/demo", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        backend.close()


if __name__ == "__main__":
    main()
