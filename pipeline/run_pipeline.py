from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.data_fetcher import fetch_macro_data, fetch_price_data
from pipeline.news_fetcher import fetch_news
from pipeline.notifier import send_discord_summary
from pipeline.runtime import get_config_provider, get_storage_provider
from pipeline.sentiment import score_sentiment
from pipeline.social_fetcher import fetch_social
from pipeline.technical import compute_technicals
from pipeline.ai_analyst import generate_analysis

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)


def run(tickers: list[str] | None = None, *, run_id: str | None = None, source: str = "manual") -> list[dict[str, Any]]:
    run_id = run_id or str(uuid.uuid4())
    config = get_config_provider()
    storage = get_storage_provider()
    settings = config.pipeline_settings()
    storage.init()
    raw_watchlist = tickers if tickers is not None else storage.load_watchlist()
    if raw_watchlist is None:
        raw_watchlist = config.default_watchlist()
    watchlist = [t.upper().strip() for t in raw_watchlist if t.strip()]
    storage.create_run_status(run_id, "RUNNING", source, watchlist)
    log.info("pipeline_start run_id=%s source=%s tickers=%s", run_id, source, watchlist)

    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    try:
        for ticker in watchlist:
            try:
                result = process_ticker(ticker, settings.weights)
                results.append(result)
                storage.save_run(result)
                log.info("ticker_complete run_id=%s ticker=%s score=%s", run_id, ticker, result.get("aggregate_score"))
            except Exception as exc:
                failures.append({"ticker": ticker, "error": str(exc)})
                log.exception("ticker_failed run_id=%s ticker=%s", run_id, ticker)
        status = "SUCCEEDED" if not failures else "PARTIAL_FAILURE" if results else "FAILED"
        storage.update_run_status(run_id, status, processed=len(results), failed=len(failures), failures=failures, completed_at=datetime.now(timezone.utc).isoformat())
        send_discord_summary(results)
        return results
    except Exception as exc:
        storage.update_run_status(run_id, "FAILED", error=str(exc), completed_at=datetime.now(timezone.utc).isoformat())
        raise


def process_ticker(ticker: str, weights: dict[str, float] | None = None) -> dict[str, Any]:
    weights = weights or {"technical": 0.40, "sentiment": 0.35, "macro": 0.25}
    price_data = fetch_price_data(ticker)
    technicals = compute_technicals(price_data)
    news_items = fetch_news(ticker)
    social_posts = fetch_social(ticker)
    macro = fetch_macro_data()
    sentiment = score_sentiment(news_items, social_posts, ticker)
    analysis = generate_analysis(ticker, price_data, technicals, sentiment, macro)
    aggregate_score = round(
        technicals["composite_score"] * weights["technical"]
        + sentiment["composite_score"] * weights["sentiment"]
        + macro["composite_score"] * weights["macro"]
    )
    return {
        "ticker": ticker,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "price_data": price_data,
        "technicals": technicals,
        "sentiment": sentiment,
        "macro": macro,
        "news": news_items,
        "social": social_posts,
        "analysis": analysis,
        "aggregate_score": aggregate_score,
    }


def lambda_handler(event, context):
    run_id = (event or {}).get("run_id") or getattr(context, "aws_request_id", None) or str(uuid.uuid4())
    tickers = (event or {}).get("tickers")
    source = (event or {}).get("source", "lambda")
    results = run(tickers=tickers, run_id=run_id, source=source)
    return {"run_id": run_id, "status": "COMPLETED", "processed": len(results)}


if __name__ == "__main__":
    run(source="local-cli")
