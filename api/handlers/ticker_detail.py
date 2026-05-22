from __future__ import annotations

from api.handlers.common import handle_errors, response, error_response, storage


@handle_errors
def detail_handler(event, context):
    ticker = (event.get("pathParameters") or {}).get("ticker", "").upper()
    result = storage().get_latest_run(ticker)
    if not result:
        return error_response(404, "not_found", f"No data found for {ticker}.")
    return response(200, result)


@handle_errors
def history_handler(event, context):
    ticker = (event.get("pathParameters") or {}).get("ticker", "").upper()
    days = int((event.get("queryStringParameters") or {}).get("days", 30))
    return response(200, {"ticker": ticker, "history": storage().get_history(ticker, days)})
