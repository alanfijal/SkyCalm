"""Shared HTTP response contract for Lambda and the local preview."""

import json
import logging
from urllib.parse import parse_qsl

from services.forecast.api import RequestError, respond

logger = logging.getLogger(__name__)


def response(method: str, path: str, query_string: str, store, request_id: str) -> dict:
    try:
        if method != "GET":
            raise RequestError("method", "Use GET for forecast requests.", 405)
        if len(query_string) > 1500:
            raise RequestError("invalid_query", "The request is too long.", 400)
        try:
            pairs = parse_qsl(query_string, keep_blank_values=True, max_num_fields=8)
        except ValueError as exc:
            raise RequestError("invalid_query", "Invalid query parameters.", 400) from exc
        query = dict(pairs)
        if len(query) != len(pairs):
            raise RequestError("invalid_query", "Supply each field only once.", 400)
        payload = respond(path, query, store)
        status = 200
    except RequestError as exc:
        payload, status = {"code": exc.code, "message": str(exc)}, exc.status
    except Exception:
        logger.error(json.dumps({"event": "forecast.unavailable", "requestId": request_id}))
        payload, status = (
            {"code": "unavailable", "message": "The weather grid is temporarily unavailable."},
            503,
        )
    run_id = payload.get("run", {}).get("runId")
    logger.info(
        json.dumps(
            {
                "event": "forecast.request",
                "requestId": request_id,
                "runId": run_id,
                "status": status,
            }
        )
    )
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        "body": json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
    }
