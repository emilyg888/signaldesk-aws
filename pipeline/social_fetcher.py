"""
Social sentiment fetcher — X (Twitter) API v2, pay-per-use.
Searches for recent posts mentioning each ticker.
Read-only. No posts are stored permanently — text is passed to
OpenAI for sentiment scoring then discarded.

Cost estimate: ~$0.01 per tweet read, deduplicated per 24h UTC window.
For 5 tickers × 50 tweets = ~$0.25/day = ~$7.50/month maximum.
"""

import logging
import requests
from datetime import datetime, timezone, timedelta

from pipeline.config import API_KEYS, SETTINGS

log = logging.getLogger(__name__)

# X API v2 base
X_BASE = "https://api.x.com/2"

# Ticker → search query mapping
# $ cashtag is the most signal-rich format on X for financial content
QUERY_MAP = {
    "AAPL":     "$AAPL OR #AAPL Apple stock",
    "NVDA":     "$NVDA OR #NVDA Nvidia stock",
    "TSLA":     "$TSLA OR #TSLA Tesla stock",
    "MSFT":     "$MSFT OR #MSFT Microsoft stock",
    "AMZN":     "$AMZN OR #AMZN Amazon stock",
    "GOOGL":    "$GOOGL OR #GOOGL Google stock",
    "META":     "$META OR #META Meta stock",
    "BTC-USD":  "$BTC OR #Bitcoin OR #BTC crypto",
    "ETH-USD":  "$ETH OR #Ethereum OR #ETH crypto",
    "SOL-USD":  "$SOL OR #Solana OR #SOL crypto",
    "EURUSD=X": "$EURUSD OR EUR/USD forex",
    "GBPUSD=X": "$GBPUSD OR GBP/USD forex",
    "JPY=X":    "$USDJPY OR USD/JPY forex",
    "AUDUSD=X": "$AUDUSD OR AUD/USD forex",
    "GC=F":     "$GOLD OR #Gold commodity",
}


def fetch_social(ticker: str) -> list[dict]:
    """
    Fetch recent X posts mentioning the ticker.
    Returns list of post dicts with title (text), score (likes), etc.
    Returns empty list gracefully if token not set or API fails.
    """
    token = API_KEYS.get("x_bearer_token", "")
    if not token or token.startswith("YOUR_"):
        log.info(f"  X API token not configured — skipping social fetch for {ticker}")
        return []

    query = _build_query(ticker)
    if not query:
        log.warning(f"  No X query mapping for {ticker} — skipping")
        return []

    try:
        posts = _search_recent(query, ticker, token)
        log.info(f"  X API returned {len(posts)} posts for {ticker}")
        return posts
    except Exception as e:
        log.warning(f"  X API fetch failed for {ticker}: {e}")
        return []


def _build_query(ticker: str) -> str:
    """Build X search query for a ticker."""
    # Use known mapping first
    if ticker in QUERY_MAP:
        return QUERY_MAP[ticker]

    # Generic fallback — strip common suffixes and use cashtag
    clean = ticker.replace("-USD", "").replace("=X", "").replace(".X", "")
    return f"${clean} OR #{clean}"


def _search_recent(query: str, ticker: str, token: str) -> list[dict]:
    """
    Call X API v2 recent search endpoint.
    Returns last 2 hours of posts, filtered for quality.
    """
    # Search window: last 2 hours (enough for morning sentiment)
    start_time = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    # Exclude retweets, replies, and low-quality content
    full_query = (
        f"({query}) "
        f"-is:retweet -is:reply lang:en"
    )

    params = {
        "query":        full_query,
        "max_results":  SETTINGS.get("x_max_posts", 50),
        "start_time":   start_time,
        "tweet.fields": "created_at,public_metrics,lang",
        "expansions":   "author_id",
        "user.fields":  "verified,public_metrics",
        "sort_order":   "relevancy",
    }

    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(
        f"{X_BASE}/tweets/search/recent",
        params=params,
        headers=headers,
        timeout=15,
    )

    if resp.status_code == 401:
        raise ValueError("X API: invalid Bearer Token — check config.py")
    if resp.status_code == 403:
        raise ValueError("X API: access forbidden — check your plan permissions")
    if resp.status_code == 429:
        log.warning(f"  X API rate limited for {ticker} — skipping")
        return []
    if resp.status_code != 200:
        raise ValueError(f"X API returned {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    tweets = data.get("data", [])
    if not tweets:
        log.debug(f"  No X posts found for query: {full_query}")
        return []

    # Build user metrics lookup for influence filtering
    users = {
        u["id"]: u
        for u in data.get("includes", {}).get("users", [])
    }

    posts = []
    for t in tweets:
        metrics   = t.get("public_metrics", {})
        author_id = t.get("author_id", "")
        user      = users.get(author_id, {})
        user_met  = user.get("public_metrics", {})
        followers = user_met.get("followers_count", 0)

        # Filter out very low-follower accounts to reduce noise
        # Keep accounts with 100+ followers or any engagement
        likes    = metrics.get("like_count", 0)
        retweets = metrics.get("retweet_count", 0)
        if followers < 100 and likes == 0 and retweets == 0:
            continue

        # Engagement score — used for sorting/weighting
        engagement = likes + (retweets * 3) + min(followers // 1000, 20)

        posts.append({
            "title":       t.get("text", ""),           # pipeline uses "title" field
            "score":       engagement,
            "comments":    metrics.get("reply_count", 0),
            "url":         f"https://x.com/i/web/status/{t['id']}",
            "subreddit":   "x",                         # source label
            "created_at":  t.get("created_at", ""),
            "likes":       likes,
            "retweets":    retweets,
            "followers":   followers,
            "verified":    user.get("verified", False),
        })

    # Sort by engagement descending
    posts.sort(key=lambda p: p["score"], reverse=True)
    return posts[:SETTINGS.get("x_max_posts", 50)]
