from __future__ import annotations

from datetime import datetime, timezone

from api.handlers.common import handle_errors, response, storage


@handle_errors
def handler(event, context):
    results = storage().get_all_latest()
    last_run = max((item.get("run_date", "") for item in results), default=None)
    return response(200, {"status": "ok", "tickers": len(results), "last_run": last_run, "server_time": datetime.now(timezone.utc).isoformat()})
