"""
Discord webhook notifications.
Sends a daily embed summary after the pipeline completes.
"""

import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)


def send_discord_summary(results: list) -> None:
    """
    Send a Discord embed summary of pipeline results via webhook.
    Skips gracefully if webhook URL not configured or POST fails.
    """
    from pipeline.config import API_KEYS

    webhook_url = API_KEYS.get("discord_webhook", "")
    if not webhook_url or webhook_url.startswith("YOUR_"):
        log.warning("Discord webhook URL not configured — skipping Discord notification")
        return

    if not results:
        log.warning("No pipeline results to summarise — skipping Discord notification")
        return

    payload = _build_discord_payload(results)

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        log.info("Discord summary sent")
    except Exception as e:
        log.warning(f"Discord notification failed — {e}")


def _build_discord_payload(results: list) -> dict:
    sorted_results = sorted(
        results, key=lambda r: r.get("aggregate_score", 0), reverse=True
    )

    now = datetime.now()
    title = f"\U0001f4ca SignalDesk — {now.strftime('%A')} {now.strftime('%d %b %Y')}"

    # Determine embed colour based on majority bias
    bullish = sum(1 for r in sorted_results if r.get("aggregate_score", 50) >= 60)
    bearish = sum(1 for r in sorted_results if r.get("aggregate_score", 50) <= 40)
    if bullish > bearish:
        color = 0x00D17A  # green
    elif bearish > bullish:
        color = 0xFF4D6D  # red
    else:
        color = 0x7A8494  # grey

    fields = []
    for r in sorted_results:
        ticker = r.get("ticker", "?")
        score = r.get("aggregate_score", 0)
        bias = r.get("analysis", {}).get("bias", "Neutral")
        emoji = _bias_emoji(score)
        action = r.get("analysis", {}).get("suggested_action", "")
        if len(action) > 80:
            action = action[:77] + "..."
        value = f"{emoji} {score}/100 — {bias}"
        if action:
            value += f"\n{action}"
        fields.append({"name": ticker, "value": value, "inline": True})

    macro = results[0].get("macro", {})
    vix = macro.get("vix")
    us10y = macro.get("us10y")
    macro_score = macro.get("composite_score")

    footer_parts = []
    footer_parts.append(f"VIX {vix} ({_vix_label(vix)})" if vix is not None else "VIX —")
    footer_parts.append(f"10Y {us10y}%" if us10y is not None else "10Y —")
    footer_parts.append(f"Macro {macro_score}/100" if macro_score is not None else "Macro —")

    return {
        "embeds": [{
            "title": title,
            "color": color,
            "fields": fields,
            "footer": {"text": " · ".join(footer_parts)},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }


def _format_message(results: list) -> str:
    now  = datetime.now()
    day  = now.strftime("%A")
    date = now.strftime("%d %b %Y")

    sorted_results = sorted(
        results, key=lambda r: r.get("aggregate_score", 0), reverse=True
    )

    lines = [f"📊 SignalDesk — {day} {date}", ""]

    for r in sorted_results:
        ticker = r.get("ticker", "?")
        score  = r.get("aggregate_score", 0)
        bias   = r.get("analysis", {}).get("bias", "Neutral")
        emoji  = _bias_emoji(score)
        lines.append(f"{ticker}  {score} {emoji} {bias}")

    lines.append("")

    top        = sorted_results[0]
    top_ticker = top.get("ticker", "?")
    top_action = top.get("analysis", {}).get("suggested_action", "")
    top_line   = f"Top signal: {top_ticker} — {top_action}" if top_action else f"Top signal: {top_ticker}"
    lines.append(top_line)

    macro     = results[0].get("macro", {})
    vix       = macro.get("vix")
    us10y     = macro.get("us10y")
    vix_str   = f"VIX {vix} ({_vix_label(vix)})" if vix   is not None else "VIX —"
    yield_str = f"10Y {us10y}%"                   if us10y is not None else "10Y —"
    lines.append(f"Macro: {vix_str}, {yield_str}")

    lines.append("")
    lines.append("Full dashboard → http://localhost:8088")

    return "\n".join(lines)


def _bias_emoji(score: int) -> str:
    if score >= 60:
        return "🟢"
    if score <= 40:
        return "🔴"
    return "⚪"


def _vix_label(vix) -> str:
    if vix is None:
        return "—"
    if vix < 20:
        return "Low Fear"
    if vix < 30:
        return "Moderate"
    return "Elevated"
