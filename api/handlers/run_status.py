from __future__ import annotations

from api.handlers.common import handle_errors, response, error_response, storage


@handle_errors
def handler(event, context):
    run_id = (event.get("pathParameters") or {}).get("run_id", "")
    status = storage().get_run_status(run_id)
    if not status:
        return error_response(404, "not_found", f"No run status found for {run_id}.")
    return response(200, status)
