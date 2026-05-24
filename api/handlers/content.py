from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import boto3

from api.handlers.common import handle_errors, response, error_response, storage


_TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-=]{0,23}$")


@handle_errors
def earnings_story_handler(event, context):
    ticker = _ticker_from_event(event)
    run_data = storage().get_latest_run(ticker)
    if not run_data:
        return error_response(404, "not_found", f"No data found for {ticker}.")
    content = _generate_content(ticker, run_data, "earnings_story", _fallback_earnings_story(ticker, run_data))
    return response(200, {"ticker": ticker, "generated_at": datetime.now(timezone.utc).isoformat(), "content": content})


@handle_errors
def news_draft_handler(event, context):
    ticker = _ticker_from_event(event)
    run_data = storage().get_latest_run(ticker)
    if not run_data:
        return error_response(404, "not_found", f"No data found for {ticker}.")
    content = _generate_content(ticker, run_data, "news_draft", _fallback_news_draft(ticker, run_data))
    return response(200, {"ticker": ticker, "generated_at": datetime.now(timezone.utc).isoformat(), "content": content})


def _ticker_from_event(event: dict[str, Any]) -> str:
    ticker = str((event.get("pathParameters") or {}).get("ticker", "")).upper().strip()
    if not _TICKER_PATTERN.match(ticker):
        raise ValueError("Invalid ticker.")
    return ticker


def _generate_content(ticker: str, run_data: dict[str, Any], content_type: str, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        prompt = _content_prompt(ticker, run_data, content_type)
        raw = _bedrock_converse(prompt)
        payload = json.loads(raw.strip().replace("```json", "").replace("```", "").strip())
        return _normalize_content(content_type, payload, fallback)
    except Exception:
        return fallback


def _bedrock_converse(prompt: str) -> str:
    client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "ap-southeast-2"))
    response = client.converse(
        modelId=os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 1200, "temperature": 0.2},
    )
    return response["output"]["message"]["content"][0]["text"]


def _content_prompt(ticker: str, run_data: dict[str, Any], content_type: str) -> str:
    schemas = {
        "earnings_story": {
            "headline": "string",
            "dek": "string",
            "body": ["paragraph"],
            "latest_earnings_report": {"report_date": "string", "summary": "string", "source_links": [{"title": "string", "url": "string"}]},
            "watch_items": ["string"],
            "disclosure_note": "string",
        },
        "news_draft": {
            "headline": "string",
            "summary": "string",
            "article": ["paragraph"],
            "social_blurb": "string",
            "editor_checks": ["string"],
        },
    }
    compact = {
        "role": "SignalDesk finance editor",
        "instruction": "Return only valid JSON matching the schema. Use only supplied data. Flag verification gaps. Do not provide financial advice.",
        "content_type": content_type,
        "schema": schemas[content_type],
        "payload": {
            "ticker": ticker,
            "run_date": run_data.get("run_date"),
            "price_data": run_data.get("price_data", {}),
            "technicals": run_data.get("technicals", {}),
            "sentiment": run_data.get("sentiment", {}),
            "macro": run_data.get("macro", {}),
            "analysis": run_data.get("analysis", {}),
            "aggregate_score": run_data.get("aggregate_score"),
            "recent_news": (run_data.get("news") or [])[:8],
        },
    }
    return json.dumps(compact, default=str)


def _normalize_content(content_type: str, payload: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return fallback
    if content_type == "earnings_story":
        return {
            "headline": str(payload.get("headline") or fallback["headline"]),
            "dek": str(payload.get("dek") or fallback["dek"]),
            "body": _string_list(payload.get("body"), fallback["body"], 5),
            "latest_earnings_report": _earnings_report(payload.get("latest_earnings_report"), fallback["latest_earnings_report"]),
            "watch_items": _string_list(payload.get("watch_items"), fallback["watch_items"], 8),
            "disclosure_note": str(payload.get("disclosure_note") or fallback["disclosure_note"]),
        }
    return {
        "headline": str(payload.get("headline") or fallback["headline"]),
        "summary": str(payload.get("summary") or fallback["summary"]),
        "article": _string_list(payload.get("article"), fallback["article"], 6),
        "social_blurb": str(payload.get("social_blurb") or fallback["social_blurb"]),
        "editor_checks": _string_list(payload.get("editor_checks"), fallback["editor_checks"], 8),
    }


def _string_list(value: Any, fallback: list[str], limit: int) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned[:limit] or fallback


def _earnings_report(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return fallback
    links = []
    for item in value.get("source_links") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if url.startswith(("http://", "https://")):
            links.append({"title": str(item.get("title") or url), "url": url})
    return {
        "report_date": str(value.get("report_date") or fallback["report_date"]),
        "summary": str(value.get("summary") or fallback["summary"]),
        "source_links": links[:5],
    }


def _fallback_earnings_story(ticker: str, run_data: dict[str, Any]) -> dict[str, Any]:
    analysis = run_data.get("analysis", {})
    price = run_data.get("price_data", {})
    return {
        "headline": f"{ticker} earnings angle needs review after latest signal run",
        "dek": f"{ticker} traded {float(price.get('change_pct') or 0):+.2f}% in the latest run, with a {analysis.get('bias', 'Neutral')} model bias.",
        "body": [
            f"{ticker}'s latest SignalDesk run points to {analysis.get('bias', 'Neutral').lower()} short-term positioning.",
            analysis.get("narrative", "No model narrative was available for this run."),
            "No verified earnings release was included in the stored data, so this draft needs source review before use.",
        ],
        "latest_earnings_report": {
            "report_date": "Not available",
            "summary": "No recent corporate earnings report was present in the stored news data.",
            "source_links": [],
        },
        "watch_items": analysis.get("key_catalysts") or ["Revenue", "EPS", "Management guidance"],
        "disclosure_note": "Fallback copy generated from stored SignalDesk data.",
    }


def _fallback_news_draft(ticker: str, run_data: dict[str, Any]) -> dict[str, Any]:
    analysis = run_data.get("analysis", {})
    news = run_data.get("news") or []
    first_headline = news[0].get("headline") if news and isinstance(news[0], dict) else "latest market data"
    return {
        "headline": f"{ticker} signal update: {analysis.get('bias', 'Neutral')} bias after {first_headline}",
        "summary": analysis.get("narrative", "No model narrative was available for this run."),
        "article": [
            f"{ticker}'s latest SignalDesk run shows an aggregate score of {run_data.get('aggregate_score', 'N/A')}.",
            analysis.get("narrative", "The stored run did not include a narrative summary."),
            f"The most recent fetched headline was: {first_headline}.",
        ],
        "social_blurb": f"{ticker}: {analysis.get('bias', 'Neutral')} signal in the latest SignalDesk run.",
        "editor_checks": ["Verify all prices and timestamps", "Confirm company-specific claims", "Review source links before publishing"],
    }
