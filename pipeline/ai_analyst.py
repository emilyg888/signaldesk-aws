"""
AI Analyst — generates narrative insight, short-term forecast, and
first-pass editorial content via OpenAI ChatGPT.
Sentiment source: NewsAPI only (Reddit/StockTwits dropped).
"""

import logging
import json
from openai import OpenAI
from pipeline.config import OPENAI

log = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI["api_key"]) if OPENAI["api_key"] else None

SYSTEM_PROMPT = """You are an expert quantitative analyst and market strategist.
You receive structured data on a financial asset including technical indicators,
sentiment scores, macro environment, and recent news.

Your job: produce a SHORT-TERM (1–5 day) trading analysis.

Respond ONLY with valid JSON — no preamble, no markdown fences. Format:
{
  "bias": "Bullish" | "Bearish" | "Neutral",
  "conviction": "High" | "Medium" | "Low",
  "narrative": "<2–3 sentence synthesis of technical + sentiment + macro>",
  "key_risks": ["risk1", "risk2"],
  "key_catalysts": ["catalyst1", "catalyst2"],
  "forecast": [
    {"day": "D+1", "direction": "Up" | "Down" | "Flat", "magnitude": "<e.g. +0.8%>", "confidence": <int 50-85>},
    {"day": "D+2", "direction": "...", "magnitude": "...", "confidence": <int>},
    {"day": "D+3", "direction": "...", "magnitude": "...", "confidence": <int>},
    {"day": "D+4", "direction": "...", "magnitude": "...", "confidence": <int>},
    {"day": "D+5", "direction": "...", "magnitude": "...", "confidence": <int>}
  ],
  "key_levels": {
    "support": ["level1", "level2"],
    "resistance": ["level1", "level2"]
  },
  "suggested_action": "<e.g. Watch for breakout above resistance at X>"
}"""


def generate_analysis(
    ticker: str,
    price_data: dict,
    technicals: dict,
    sentiment: dict,
    macro: dict,
) -> dict:
    try:
        from pipeline.runtime import runtime_mode, get_ai_client
        if runtime_mode() == "aws":
            return get_ai_client().generate_analysis(ticker=ticker, price_data=price_data, technicals=technicals, sentiment=sentiment, macro=macro)
    except Exception as e:
        log.warning(f"  AWS analysis provider failed for {ticker}: {e}")
        return _fallback_analysis(ticker, technicals, sentiment)
    prompt = _build_prompt(ticker, price_data, technicals, sentiment, macro)

    log.debug(f"  Calling OpenAI analysis model for {ticker}")
    try:
        resp = client.chat.completions.create(
            model=OPENAI["analysis_model"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=OPENAI["temperature"],
            max_tokens=OPENAI["max_tokens"],
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        return _normalize_analysis(parsed, ticker, technicals, sentiment)

    except json.JSONDecodeError as e:
        log.warning(f"  Analysis model returned non-JSON for {ticker}: {e}")
        return _fallback_analysis(ticker, technicals, sentiment)
    except Exception as e:
        log.error(f"  OpenAI analysis call failed for {ticker}: {e}")
        return _fallback_analysis(ticker, technicals, sentiment)


EARNINGS_STORY_PROMPT = """You are a markets reporter writing a corporate earnings story.
Use only the provided structured data. If earnings figures are not present,
state clearly that this is a market-data driven earnings preview/angle, not
reported company earnings.

Respond ONLY with valid JSON — no preamble, no markdown fences. Format:
{
  "headline": "<specific headline>",
  "dek": "<one sentence summary>",
  "body": ["paragraph 1", "paragraph 2", "paragraph 3"],
  "latest_earnings_report": {
    "report_date": "<YYYY-MM-DD, Month D, YYYY, or Not available>",
    "summary": "<2-3 sentence summary of the most recent corporate earnings report found in the provided data>",
    "source_links": [{"title": "<source title>", "url": "<source url>"}]
  },
  "watch_items": ["item1", "item2", "item3"],
  "disclosure_note": "<limitations/source note>"
}"""

NEWS_DRAFT_PROMPT = """You are a financial news editor preparing first-pass copy.
Generate publishable-but-unverified draft content from the provided ticker data.
Avoid unsupported claims, keep attribution to the supplied data, and flag gaps.

Respond ONLY with valid JSON — no preamble, no markdown fences. Format:
{
  "headline": "<specific headline>",
  "summary": "<2 sentence summary>",
  "article": ["paragraph 1", "paragraph 2", "paragraph 3", "paragraph 4"],
  "social_blurb": "<short social copy>",
  "editor_checks": ["check1", "check2", "check3"]
}"""


def generate_earnings_story(ticker: str, run_data: dict) -> dict:
    try:
        from pipeline.runtime import runtime_mode, get_ai_client
        if runtime_mode() == "aws":
            return get_ai_client().generate_earnings_story(ticker=ticker, run_data=run_data)
    except Exception:
        pass
    prompt = _build_content_prompt(ticker, run_data, "earnings_story")
    fallback = _fallback_earnings_story(ticker, run_data)
    return _generate_json_content(
        ticker=ticker,
        prompt=prompt,
        system_prompt=EARNINGS_STORY_PROMPT,
        fallback=fallback,
        normalizer=_normalize_earnings_story,
    )


def generate_news_draft(ticker: str, run_data: dict) -> dict:
    try:
        from pipeline.runtime import runtime_mode, get_ai_client
        if runtime_mode() == "aws":
            return get_ai_client().generate_news_draft(ticker=ticker, run_data=run_data)
    except Exception:
        pass
    prompt = _build_content_prompt(ticker, run_data, "news_draft")
    fallback = _fallback_news_draft(ticker, run_data)
    return _generate_json_content(
        ticker=ticker,
        prompt=prompt,
        system_prompt=NEWS_DRAFT_PROMPT,
        fallback=fallback,
        normalizer=_normalize_news_draft,
    )


def _generate_json_content(ticker, prompt, system_prompt, fallback, normalizer):
    try:
        resp = client.chat.completions.create(
            model=OPENAI["content_model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=OPENAI["temperature"],
            max_tokens=OPENAI["max_tokens"],
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return normalizer(json.loads(raw), fallback)
    except json.JSONDecodeError as e:
        log.warning(f"  OpenAI content model returned non-JSON for {ticker}: {e}")
        return fallback
    except Exception as e:
        log.error(f"  OpenAI content generation failed for {ticker}: {e}")
        return fallback


def _build_content_prompt(ticker: str, run_data: dict, content_type: str) -> str:
    compact = {
        "content_type": content_type,
        "ticker": ticker,
        "run_date": run_data.get("run_date"),
        "price_data": run_data.get("price_data", {}),
        "technicals": run_data.get("technicals", {}),
        "sentiment": run_data.get("sentiment", {}),
        "macro": run_data.get("macro", {}),
        "analysis": run_data.get("analysis", {}),
        "aggregate_score": run_data.get("aggregate_score"),
        "recent_news": (run_data.get("news") or [])[:8],
    }
    return json.dumps(compact, default=str, indent=2)


def _normalize_earnings_story(payload: dict, fallback: dict) -> dict:
    if not isinstance(payload, dict):
        return fallback
    return {
        "headline": payload.get("headline") or fallback["headline"],
        "dek": payload.get("dek") or fallback["dek"],
        "body": _normalize_string_list(payload.get("body"), fallback["body"], limit=5),
        "latest_earnings_report": _normalize_earnings_report(
            payload.get("latest_earnings_report"),
            fallback["latest_earnings_report"],
        ),
        "watch_items": _normalize_string_list(payload.get("watch_items"), fallback["watch_items"], limit=6),
        "disclosure_note": payload.get("disclosure_note") or fallback["disclosure_note"],
    }


def _normalize_news_draft(payload: dict, fallback: dict) -> dict:
    if not isinstance(payload, dict):
        return fallback
    return {
        "headline": payload.get("headline") or fallback["headline"],
        "summary": payload.get("summary") or fallback["summary"],
        "article": _normalize_string_list(payload.get("article"), fallback["article"], limit=6),
        "social_blurb": payload.get("social_blurb") or fallback["social_blurb"],
        "editor_checks": _normalize_string_list(payload.get("editor_checks"), fallback["editor_checks"], limit=8),
    }


def _normalize_string_list(value, fallback, limit):
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned[:limit] or fallback


def _normalize_earnings_report(value, fallback):
    if not isinstance(value, dict):
        return fallback
    source_links = value.get("source_links")
    cleaned_links = []
    if isinstance(source_links, list):
        for item in source_links[:5]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip() or url
            if url.startswith(("http://", "https://")):
                cleaned_links.append({"title": title, "url": url})
    return {
        "report_date": value.get("report_date") or fallback["report_date"],
        "summary": value.get("summary") or fallback["summary"],
        "source_links": cleaned_links or fallback.get("source_links", []),
    }


def _fallback_earnings_story(ticker: str, run_data: dict) -> dict:
    analysis = run_data.get("analysis", {})
    price = run_data.get("price_data", {})
    latest_report = _fallback_latest_earnings_report(ticker, run_data)
    return {
        "headline": f"{ticker} earnings angle needs review after latest signal run",
        "dek": f"{ticker} traded {price.get('change_pct', 0):+.2f}% in the latest run, with a {analysis.get('bias', 'Neutral')} model bias.",
        "body": [
            f"{ticker}'s latest SignalDesk run points to {analysis.get('bias', 'Neutral').lower()} short-term positioning, based on price action, sentiment, and macro inputs.",
            analysis.get("narrative", "No model narrative was available for this run."),
            "No reported earnings statement was included in the available data, so this draft should be treated as a first-pass earnings angle or preview.",
        ],
        "latest_earnings_report": latest_report,
        "watch_items": analysis.get("key_catalysts") or ["Reported revenue", "EPS", "Management guidance"],
        "disclosure_note": "Fallback copy generated from stored market data because live AI content generation was unavailable.",
    }


def _fallback_latest_earnings_report(ticker: str, run_data: dict) -> dict:
    earnings_terms = ("earnings", "quarter", "eps", "revenue", "profit", "results")
    candidates = []
    for item in run_data.get("news") or []:
        headline = item.get("headline") or item.get("title") or ""
        summary = item.get("summary") or ""
        haystack = f"{headline} {summary}".lower()
        if any(term in haystack for term in earnings_terms):
            candidates.append(item)

    if not candidates:
        return {
            "report_date": "Not available",
            "summary": "No recent corporate earnings report was present in the stored news data. Verify the company investor-relations page or latest filing before treating this as an earnings recap.",
            "source_links": [],
        }

    latest = candidates[0]
    headline = latest.get("headline") or latest.get("title") or f"{ticker} earnings update"
    published = latest.get("published_at") or "Not available"
    source = latest.get("source") or "News source"
    url = latest.get("url") or ""
    links = [{"title": headline, "url": url}] if url.startswith(("http://", "https://")) else []
    return {
        "report_date": published[:10] if published != "Not available" else published,
        "summary": f"Most recent earnings-related item found: {headline} ({source}). Use this as a source lead and verify the actual company release date before publishing.",
        "source_links": links,
    }


def _fallback_news_draft(ticker: str, run_data: dict) -> dict:
    analysis = run_data.get("analysis", {})
    news = run_data.get("news") or []
    first_headline = news[0].get("headline") if news else "latest market data"
    return {
        "headline": f"{ticker} signal update: {analysis.get('bias', 'Neutral')} bias after {first_headline}",
        "summary": analysis.get("narrative", "No model narrative was available for this run."),
        "article": [
            f"{ticker}'s latest SignalDesk run shows an aggregate score of {run_data.get('aggregate_score', 'N/A')}.",
            analysis.get("narrative", "The stored run did not include a narrative summary."),
            f"The most recent fetched headline was: {first_headline}.",
        ],
        "social_blurb": f"{ticker}: {analysis.get('bias', 'Neutral')} signal in the latest SignalDesk run.",
        "editor_checks": ["Verify all prices and timestamps", "Confirm any company-specific claims", "Review source links before publishing"],
    }


def _build_prompt(ticker, price_data, tech, sent, macro) -> str:
    price = price_data.get("current_price", "N/A")
    chg   = price_data.get("change_pct", 0)

    # Safely get news sentiment score
    news_score = sent.get("sources", {}).get("news", {})
    news_sentiment_line = (
        f"News: {news_score.get('score', 50)}/100 — {news_score.get('label', 'Neutral')}"
    )

    lines = [
        f"Asset: {ticker}",
        f"Current price: {price} (today's change: {chg:+.2f}%)",
        "",
        "=== TECHNICAL INDICATORS ===",
        f"RSI(14): {tech.get('rsi')}",
        f"MACD: {tech.get('macd')} | Signal: {tech.get('macd_signal')} | Hist: {tech.get('macd_hist')}",
        f"EMA20: {tech.get('ema20')} | EMA50: {tech.get('ema50')} | Cross: {tech.get('ema_cross')}",
        f"Bollinger position: {tech.get('bb_position')} | Width: {tech.get('bb_width')}",
        f"ATR%: {tech.get('atr_pct')} | Volume ratio vs 20d avg: {tech.get('volume_ratio')}x",
        f"Stoch K/D: {tech.get('stoch_k')}/{tech.get('stoch_d')}",
        f"Technical composite score: {tech.get('composite_score')}/100",
        "",
        "=== SENTIMENT (NewsAPI — OpenAI scored) ===",
        f"Composite sentiment score: {sent.get('composite_score')}/100 ({sent.get('label')})",
        news_sentiment_line,
        f"Key themes: {', '.join(sent.get('key_themes', []))}",
        "",
        "=== MACRO ENVIRONMENT ===",
        f"VIX: {macro.get('vix')} | DXY: {macro.get('dxy')} | US10Y: {macro.get('us10y')}%",
        f"Fed rate: {macro.get('fed_rate')}% | CPI YoY: {macro.get('cpi_yoy')}% | GDP QoQ: {macro.get('gdp_qoq')}%",
        f"S&P 500: {macro.get('sp500')} | Gold: {macro.get('gold')}",
        f"Macro composite score: {macro.get('composite_score')}/100",
    ]

    return "\n".join(lines)


def _normalize_analysis(payload: dict, ticker: str, tech: dict, sent: dict) -> dict:
    """Fill missing analysis fields so downstream storage/UI always get a stable shape."""
    fallback = _fallback_analysis(ticker, tech, sent)

    if not isinstance(payload, dict):
        return fallback

    forecast = payload.get("forecast")
    normalized_forecast = []
    if isinstance(forecast, list):
        for i, item in enumerate(forecast[:5], start=1):
            if not isinstance(item, dict):
                continue
            normalized_forecast.append({
                "day": item.get("day", f"D+{i}"),
                "direction": item.get("direction", "Flat"),
                "magnitude": item.get("magnitude", "0%"),
                "confidence": item.get("confidence", 50),
            })

    if len(normalized_forecast) < 5:
        normalized_forecast.extend(fallback["forecast"][len(normalized_forecast):])

    key_levels = payload.get("key_levels")
    if not isinstance(key_levels, dict):
        key_levels = {}

    return {
        "bias": payload.get("bias", fallback["bias"]),
        "conviction": payload.get("conviction", fallback["conviction"]),
        "narrative": payload.get("narrative", fallback["narrative"]),
        "key_risks": payload.get("key_risks", fallback["key_risks"]),
        "key_catalysts": payload.get("key_catalysts", fallback["key_catalysts"]),
        "forecast": normalized_forecast,
        "key_levels": {
            "support": key_levels.get("support", fallback["key_levels"]["support"]),
            "resistance": key_levels.get("resistance", fallback["key_levels"]["resistance"]),
        },
        "suggested_action": payload.get("suggested_action", fallback["suggested_action"]),
    }


def _fallback_analysis(ticker, tech, sent) -> dict:
    """Minimal fallback if AI analysis generation fails."""
    score = (tech.get("composite_score", 50) + sent.get("composite_score", 50)) / 2
    bias  = "Bullish" if score >= 60 else "Bearish" if score <= 40 else "Neutral"
    return {
        "bias":       bias,
        "conviction": "Low",
        "narrative":  f"Fallback analysis - AI generation failed. Tech: {tech.get('composite_score')}/100, Sentiment: {sent.get('composite_score')}/100.",
        "key_risks":        ["AI generation unavailable"],
        "key_catalysts":    [],
        "forecast": [
            {"day": f"D+{i}", "direction": "Flat", "magnitude": "0%", "confidence": 50}
            for i in range(1, 6)
        ],
        "key_levels":       {"support": [], "resistance": []},
        "suggested_action": "Check AI provider configuration and retry.",
    }
