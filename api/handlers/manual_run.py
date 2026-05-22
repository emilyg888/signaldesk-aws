from __future__ import annotations

import json
import os
import uuid

import boto3
from pydantic import BaseModel, Field

from api.handlers.common import handle_errors, parse_body, response, storage


class ManualRunRequest(BaseModel):
    tickers: list[str] | None = Field(default=None, max_length=100)


@handle_errors
def handler(event, context):
    body = ManualRunRequest.model_validate(parse_body(event) or {})
    run_id = str(uuid.uuid4())
    tickers = [ticker.upper().strip() for ticker in body.tickers or [] if ticker.strip()] or None
    storage().create_run_status(run_id, "STARTED", "manual-api", tickers)
    function_name = os.getenv("SIGNALDESK_PIPELINE_FUNCTION_NAME")
    if function_name:
        boto3.client("lambda").invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps({"run_id": run_id, "tickers": tickers, "source": "manual-api"}).encode(),
        )
    return response(202, {"run_id": run_id, "status": "STARTED"})
