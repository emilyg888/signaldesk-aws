"""
Sentiment scoring using OpenAI ChatGPT.
Sources:
  - NewsAPI headlines  (always available, 100% weight when X unavailable)
  - X posts            (when Bearer Token configured, blended in)

Weighting when both sources available:
  - News: 55%   X: 45%
Weighting when only news:
  - News: 100%
"""

import logging
import json
from openai import OpenAI
from pipeline.config import OPENAI, API_KEYS

log = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI["api_key"]) if OPENAI["api_key"] else None

SYSTEM_PROMPT = """You are a financial sentiment analyser.
Given a list of texts about a financial asset, score the overall sentiment.
Respond ONLY with valid JSON — no preamble, no markdown fences.
Format: {"score": <int 0-100>, "label": "<Bearish|Neutral|Bullish>", "key_themes": ["theme1","theme2"]}
Where 0=extremely bearish, 50=neutral, 100=extremely bullish."""


def score_sentiment(news_items: list, social_posts: list, ticker: str) -> dict:
    """
    Score sentiment from news headlines and X posts. Local mode preserves the
    original OpenAI-compatible behavior; AWS mode routes through the provider
    adapter so Bedrock validation/safety gates are used.
    """
    try:
        from pipeline.runtime import runtime_mode
        if runtime_mode() == "aws":
            return _score_sentiment_provider(news_items, social_posts, ticker)
    except Exception:
        pass
    has_x = bool(social_posts)
    has_news = bool(news_items)

    news_score = _score_batch(news_items, "headline", ticker, "news") if has_news \
        else {"score": 50, "label": "Neutral", "key_themes": []}

    x_score = _score_batch(social_posts, "title", ticker, "X") if has_x \
        else {"score": 50, "label": "Neutral", "key_themes": []}

    # Weighted blend
    if has_x and has_news:
        composite = round(news_score["score"] * 0.55 + x_score["score"] * 0.45)
        log.info(f"  Sentiment blended — news: {news_score['score']} X: {x_score['score']} → {composite}")
    elif has_news:
        composite = news_score["score"]
        log.info(f"  Sentiment from news only — {composite}")
    elif has_x:
        composite = x_score["score"]
        log.info(f"  Sentiment from X only — {composite}")
    else:
        composite = 50
        log.warning(f"  No sentiment sources available for {ticker} — defaulting to neutral")

    label = "Bullish" if composite >= 60 else "Bearish" if composite <= 40 else "Neutral"

    # Merge key themes from both sources, deduplicated
    all_themes = news_score.get("key_themes", []) + x_score.get("key_themes", [])
    seen = set()
    unique_themes = [
        t for t in all_themes
        if not (t.lower() in seen or seen.add(t.lower()))
    ][:6]

    return {
        "composite_score": composite,
        "label":           label,
        "sources": {
            "news": news_score,
            "x":    x_score if has_x else None,
        },
        "key_themes": unique_themes,
    }


def _score_batch(items: list, text_field: str, ticker: str, source_name: str) -> dict:
    if not items:
        log.warning(f"  No {source_name} items to score for {ticker}")
        return {"score": 50, "label": "Neutral", "key_themes": []}

    texts = [item.get(text_field, "") for item in items[:20] if item.get(text_field)]
    if not texts:
        return {"score": 50, "label": "Neutral", "key_themes": []}

    texts_block = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    user_msg    = f"Asset: {ticker}\nSource: {source_name}\n\nTexts:\n{texts_block}"

    log.debug(f"  Scoring {len(texts)} {source_name} items for {ticker}")

    try:
        resp = client.chat.completions.create(
            model=OPENAI["sentiment_model"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        raw    = resp.choices[0].message.content.strip()
        raw    = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)

        return {
            "score":      int(parsed.get("score", 50)),
            "label":      parsed.get("label", "Neutral"),
            "key_themes": parsed.get("key_themes", []),
        }

    except json.JSONDecodeError as e:
        log.warning(f"  OpenAI returned non-JSON for {source_name}/{ticker}: {e}")
        return {"score": 50, "label": "Neutral", "key_themes": []}
    except Exception as e:
        log.error(f"  OpenAI call failed for {source_name}/{ticker}: {e}")
        return {"score": 50, "label": "Neutral", "key_themes": []}


def _score_sentiment_provider(news_items: list, social_posts: list, ticker: str) -> dict:
    from pipeline.runtime import get_ai_client
    provider = get_ai_client()
    has_x = bool(social_posts)
    has_news = bool(news_items)
    news_score = provider.score_sentiment_batch(ticker=ticker, source_name="news", texts=[i.get("headline", "") for i in news_items[:20] if i.get("headline")]) if has_news else {"score": 50, "label": "Neutral", "key_themes": []}
    x_score = provider.score_sentiment_batch(ticker=ticker, source_name="X", texts=[i.get("title", "") for i in social_posts[:20] if i.get("title")]) if has_x else {"score": 50, "label": "Neutral", "key_themes": []}
    if has_x and has_news:
        composite = round(news_score["score"] * 0.55 + x_score["score"] * 0.45)
    elif has_news:
        composite = news_score["score"]
    elif has_x:
        composite = x_score["score"]
    else:
        composite = 50
    label = "Bullish" if composite >= 60 else "Bearish" if composite <= 40 else "Neutral"
    all_themes = news_score.get("key_themes", []) + x_score.get("key_themes", [])
    seen = set()
    unique_themes = [t for t in all_themes if not (str(t).lower() in seen or seen.add(str(t).lower()))][:6]
    return {"composite_score": composite, "label": label, "sources": {"news": news_score, "x": x_score if has_x else None}, "key_themes": unique_themes}
