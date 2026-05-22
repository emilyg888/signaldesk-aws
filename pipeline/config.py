"""Safe local configuration for SignalDesk AWS.

This module intentionally reads secrets from environment variables only. It is
kept for compatibility with the original local modules and tests; AWS runtime
code should prefer ConfigProvider implementations.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
WATCHLIST_FILE = ROOT / "data" / "watchlist.json"
DEFAULT_WATCHLIST = ["AAPL", "NVDA", "TSLA", "BTC-USD", "EURUSD=X"]

OPENAI = {
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "analysis_model": os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-4o-mini"),
    "sentiment_model": os.getenv("OPENAI_SENTIMENT_MODEL", "gpt-4o-mini"),
    "content_model": os.getenv("OPENAI_CONTENT_MODEL", "gpt-4o-mini"),
    "temperature": float(os.getenv("SIGNALDESK_TEMPERATURE", "0.2")),
    "max_tokens": int(os.getenv("SIGNALDESK_MAX_TOKENS", "1200")),
}
LM_STUDIO = OPENAI

SETTINGS = {
    "weights": {
        "technical": float(os.getenv("SIGNALDESK_WEIGHT_TECHNICAL", "0.40")),
        "sentiment": float(os.getenv("SIGNALDESK_WEIGHT_SENTIMENT", "0.35")),
        "macro": float(os.getenv("SIGNALDESK_WEIGHT_MACRO", "0.25")),
    },
    "lookback_days": int(os.getenv("SIGNALDESK_LOOKBACK_DAYS", "60")),
    "forecast_days": int(os.getenv("SIGNALDESK_FORECAST_DAYS", "5")),
    "news_max_items": int(os.getenv("SIGNALDESK_NEWS_MAX_ITEMS", "20")),
    "reddit_max_posts": int(os.getenv("SIGNALDESK_REDDIT_MAX_POSTS", "50")),
}

API_KEYS = {
    "fred": os.getenv("FRED_API_KEY", ""),
    "newsapi": os.getenv("NEWSAPI_KEY", ""),
    "x_bearer_token": os.getenv("X_BEARER_TOKEN", "test-token"),
    "discord_webhook": os.getenv("DISCORD_WEBHOOK_URL", ""),
    "reddit_client_id": os.getenv("REDDIT_CLIENT_ID", ""),
    "reddit_client_secret": os.getenv("REDDIT_CLIENT_SECRET", ""),
    "reddit_user_agent": os.getenv("REDDIT_USER_AGENT", "SignalDeskAWS/1.0"),
}

PATHS = {
    "db": ROOT / "data" / "db" / "signaldesk.db",
    "cache": ROOT / "data" / "cache",
    "logs": ROOT / "logs",
}


def load_watchlist() -> list[str]:
    if WATCHLIST_FILE.exists():
        return json.loads(WATCHLIST_FILE.read_text())
    return DEFAULT_WATCHLIST.copy()


def save_watchlist(tickers: list[str]) -> None:
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_FILE.write_text(json.dumps([t.upper().strip() for t in tickers if t.strip()], indent=2))
