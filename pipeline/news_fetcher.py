"""
News fetcher via NewsAPI (free tier: 100 req/day).
Falls back to yfinance news if NewsAPI key not set.
"""

import logging
from datetime import datetime, timedelta

import yfinance as yf

from pipeline.config import API_KEYS, SETTINGS

log = logging.getLogger(__name__)

# Map tickers to good search queries
QUERY_MAP = {
    "BTC-USD":  "Bitcoin BTC",
    "ETH-USD":  "Ethereum ETH",
    "EURUSD=X": "EUR/USD euro dollar",
    "GBPUSD=X": "GBP/USD pound sterling",
    "JPY=X":    "USD/JPY yen",
    "GC=F":     "Gold price",
}


def fetch_news(ticker: str) -> list[dict]:
    key = API_KEYS.get("newsapi", "")
    if key and not key.startswith("YOUR_"):
        items = _fetch_newsapi(ticker, key)
        if items:
            return items

    # Fallback: yfinance news (no key needed)
    return _fetch_yf_news(ticker)


def _fetch_newsapi(ticker: str, key: str) -> list[dict]:
    try:
        import requests
        query = QUERY_MAP.get(ticker, ticker.replace("-USD", "").replace("=X", ""))
        from_date = (datetime.today() - timedelta(days=2)).strftime("%Y-%m-%d")

        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q":        query,
                "from":     from_date,
                "sortBy":   "publishedAt",
                "language": "en",
                "pageSize": SETTINGS["news_max_items"],
                "apiKey":   key,
            },
            timeout=10,
        )
        data = resp.json()

        if data.get("status") != "ok":
            log.warning(f"  NewsAPI error: {data.get('message')}")
            return []

        items = []
        for a in data.get("articles", []):
            items.append({
                "headline": a.get("title", ""),
                "source":   a.get("source", {}).get("name", ""),
                "url":      a.get("url", ""),
                "published_at": a.get("publishedAt", ""),
                "summary":  a.get("description", ""),
            })
        log.debug(f"  NewsAPI returned {len(items)} articles for {ticker}")
        return items

    except Exception as e:
        log.warning(f"  NewsAPI fetch failed: {e}")
        return []


def _fetch_yf_news(ticker: str) -> list[dict]:
    try:
        t = yf.Ticker(ticker)
        raw = t.news or []
        items = []
        for n in raw[:SETTINGS["news_max_items"]]:
            items.append({
                "headline":    n.get("title", ""),
                "source":      n.get("publisher", ""),
                "url":         n.get("link", ""),
                "published_at": datetime.fromtimestamp(n.get("providerPublishTime", 0)).isoformat(),
                "summary":     "",
            })
        log.debug(f"  yfinance news returned {len(items)} items for {ticker}")
        return items
    except Exception as e:
        log.warning(f"  yfinance news fetch failed for {ticker}: {e}")
        return []
