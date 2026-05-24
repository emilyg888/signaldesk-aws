from __future__ import annotations

from api.handlers.common import handle_errors, parse_body, response, storage


def _parse_tickers(body: dict) -> list[str]:
    raw_tickers = body.get("tickers", [])
    if raw_tickers is None:
        raw_tickers = []
    if not isinstance(raw_tickers, list):
        raise ValueError("tickers must be a list.")
    if len(raw_tickers) > 100:
        raise ValueError("tickers cannot contain more than 100 symbols.")
    return [str(ticker).upper().strip() for ticker in raw_tickers if str(ticker).strip()]


@handle_errors
def get_handler(event, context):
    return response(200, {"tickers": storage().load_watchlist()})


@handle_errors
def update_handler(event, context):
    tickers = _parse_tickers(parse_body(event))
    storage().save_watchlist(tickers)
    return response(200, {"tickers": tickers, "saved": True})
