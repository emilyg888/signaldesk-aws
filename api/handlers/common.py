from __future__ import annotations

import json
import math
import os
from typing import Any

from pipeline.runtime import get_storage_provider


def clean_nan(obj: Any) -> Any:
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj


def parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if body is None:
        return {}
    if isinstance(body, dict):
        return body
    if isinstance(body, str) and body.strip():
        return json.loads(body)
    return {}


def response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status_code, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"}, "body": json.dumps(clean_nan(payload), default=str)}


def error_response(status_code: int, code: str, message: str) -> dict[str, Any]:
    return response(status_code, {"error": {"code": code, "message": message}})


def handle_errors(fn):
    def wrapper(event, context):
        try:
            return fn(event or {}, context)
        except ValueError as exc:
            code = getattr(exc, "code", "bad_request")
            message = getattr(exc, "message", str(exc))
            return error_response(400, code, message)
        except Exception as exc:
            return error_response(500, "internal_error", str(exc) if os.getenv("SIGNALDESK_DEBUG_ERRORS") == "true" else "Internal server error.")
    return wrapper


def storage():
    provider = get_storage_provider()
    provider.init()
    return provider
