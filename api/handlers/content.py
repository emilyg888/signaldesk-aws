from __future__ import annotations

from datetime import datetime, timezone

from api.handlers.common import handle_errors, response, error_response, storage
from pipeline.ai_analyst import generate_earnings_story, generate_news_draft
from pipeline.safety.schemas import ManualGenerationRequest
from pipeline.safety.validator import validate_model_input


@handle_errors
def earnings_story_handler(event, context):
    ticker = (event.get("pathParameters") or {}).get("ticker", "").upper()
    validate_model_input(ManualGenerationRequest, {"ticker": ticker, "generation_type": "earnings_story"}, endpoint="earnings_story")
    run_data = storage().get_latest_run(ticker)
    if not run_data:
        return error_response(404, "not_found", f"No data found for {ticker}.")
    return response(200, {"ticker": ticker, "generated_at": datetime.now(timezone.utc).isoformat(), "content": generate_earnings_story(ticker, run_data)})


@handle_errors
def news_draft_handler(event, context):
    ticker = (event.get("pathParameters") or {}).get("ticker", "").upper()
    validate_model_input(ManualGenerationRequest, {"ticker": ticker, "generation_type": "news_draft"}, endpoint="news_draft")
    run_data = storage().get_latest_run(ticker)
    if not run_data:
        return error_response(404, "not_found", f"No data found for {ticker}.")
    return response(200, {"ticker": ticker, "generated_at": datetime.now(timezone.utc).isoformat(), "content": generate_news_draft(ticker, run_data)})
