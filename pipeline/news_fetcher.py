"""
News fetcher via NewsAPI (free tier: 100 req/day).
Falls back to yfinance news if NewsAPI key not set.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

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
            item = _normalize_yf_item(n)
            if item:
                items.append(item)
        log.debug(f"  yfinance news returned {len(items)} items for {ticker}")
        return items
    except Exception as e:
        log.warning(f"  yfinance news fetch failed for {ticker}: {e}")
        return []


def _normalize_yf_item(item: dict[str, Any]) -> dict[str, str] | None:
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    headline = str(content.get("title") or item.get("title") or "").strip()
    if not headline:
        return None

    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    source = str(provider.get("displayName") or item.get("publisher") or "").strip()
    url = _first_url(
        content.get("canonicalUrl"),
        content.get("clickThroughUrl"),
        item.get("canonicalUrl"),
        item.get("clickThroughUrl"),
        item.get("link"),
    )
    published_at = _published_at(
        content.get("pubDate")
        or content.get("displayTime")
        or item.get("pubDate")
        or item.get("displayTime")
        or item.get("providerPublishTime")
    )
    if not url or not published_at:
        return None
    return {
        "headline": headline,
        "source": source,
        "url": url,
        "published_at": published_at,
        "summary": str(content.get("summary") or content.get("description") or "").strip(),
    }


def _first_url(*values: Any) -> str:
    for value in values:
        url = value.get("url") if isinstance(value, dict) else value
        url = str(url or "").strip()
        if url.startswith(("http://", "https://")):
            return url
    return ""


def _published_at(value: Any) -> str:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.year > 2000:
                return parsed.isoformat()
        except ValueError:
            return ""
    return ""
