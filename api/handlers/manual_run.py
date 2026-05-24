from __future__ import annotations

import json
import os
import uuid

import boto3

from api.handlers.common import handle_errors, parse_body, response, storage


def _parse_tickers(body: dict) -> list[str] | None:
    raw_tickers = body.get("tickers")
    if raw_tickers is None:
        return None
    if not isinstance(raw_tickers, list):
        raise ValueError("tickers must be a list.")
    if len(raw_tickers) > 100:
        raise ValueError("tickers cannot contain more than 100 symbols.")
    tickers = [str(ticker).upper().strip() for ticker in raw_tickers if str(ticker).strip()]
    return tickers or None


@handle_errors
def handler(event, context):
    body = parse_body(event) or {}
    run_id = str(uuid.uuid4())
    tickers = _parse_tickers(body)
    storage().create_run_status(run_id, "STARTED", "manual-api", tickers)
    function_name = os.getenv("SIGNALDESK_PIPELINE_FUNCTION_NAME")
    if function_name:
        boto3.client("lambda").invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps({"run_id": run_id, "tickers": tickers, "source": "manual-api"}).encode(),
        )
    return response(202, {"run_id": run_id, "status": "STARTED"})
