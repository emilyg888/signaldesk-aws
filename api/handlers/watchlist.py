from __future__ import annotations

from pydantic import BaseModel, Field

from api.handlers.common import handle_errors, parse_body, response, storage


class WatchlistUpdate(BaseModel):
    tickers: list[str] = Field(default_factory=list, max_length=100)


@handle_errors
def get_handler(event, context):
    return response(200, {"tickers": storage().load_watchlist()})


@handle_errors
def update_handler(event, context):
    body = WatchlistUpdate.model_validate(parse_body(event))
    tickers = [ticker.upper().strip() for ticker in body.tickers if ticker.strip()]
    storage().save_watchlist(tickers)
    return response(200, {"tickers": tickers, "saved": True})
