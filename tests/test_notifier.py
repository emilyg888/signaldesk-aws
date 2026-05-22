"""
Unit tests for pipeline/notifier.py (Discord webhook)
"""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.notifier import (
    _bias_emoji,
    _build_discord_payload,
    _format_message,
    _vix_label,
    send_discord_summary,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_result(ticker, score, bias="Bullish", suggested_action="Buy", vix=18.5, us10y=4.2):
    return {
        "ticker": ticker,
        "aggregate_score": score,
        "analysis": {
            "bias": bias,
            "conviction": "High",
            "suggested_action": suggested_action,
        },
        "macro": {
            "vix": vix,
            "us10y": us10y,
            "composite_score": 62,
        },
    }


MULTI_RESULTS = [
    make_result("AAPL",    72, bias="Bullish",  suggested_action="Buy dips"),
    make_result("BTC-USD", 38, bias="Bearish",  suggested_action="Avoid"),
    make_result("TSLA",    55, bias="Neutral",  suggested_action="Hold"),
]

DISCORD_RESULTS = [
    make_result("AAPL",     72, bias="Bullish",  suggested_action="Buy dips near 195 support"),
    make_result("NVDA",     65, bias="Bullish",  suggested_action="Accumulate on weakness"),
    make_result("TSLA",     55, bias="Neutral",  suggested_action="Hold — wait for breakout"),
    make_result("BTC-USD",  38, bias="Bearish",  suggested_action="Avoid — below key moving averages"),
    make_result("EURUSD=X", 42, bias="Neutral",  suggested_action="Sideways range"),
]

VALID_KEYS = {
    "discord_webhook": "https://discord.com/api/webhooks/test/fake",
}


# ── _bias_emoji ──────────────────────────────────────────────────────────────

class TestBiasEmoji:
    def test_bullish_score_returns_green(self):
        assert _bias_emoji(60) == "🟢"

    def test_high_bull_score_returns_green(self):
        assert _bias_emoji(85) == "🟢"

    def test_bearish_score_returns_red(self):
        assert _bias_emoji(40) == "🔴"

    def test_low_bear_score_returns_red(self):
        assert _bias_emoji(10) == "🔴"

    def test_neutral_score_returns_white(self):
        assert _bias_emoji(50) == "⚪"

    def test_boundary_60_is_bull(self):
        assert _bias_emoji(60) == "🟢"

    def test_boundary_40_is_bear(self):
        assert _bias_emoji(40) == "🔴"

    def test_boundary_41_is_neutral(self):
        assert _bias_emoji(41) == "⚪"

    def test_boundary_59_is_neutral(self):
        assert _bias_emoji(59) == "⚪"


# ── _vix_label ───────────────────────────────────────────────────────────────

class TestVixLabel:
    def test_low_vix_returns_low_fear(self):
        assert _vix_label(15) == "Low Fear"

    def test_boundary_vix_under_20_is_low_fear(self):
        assert _vix_label(19.9) == "Low Fear"

    def test_moderate_vix(self):
        assert _vix_label(25) == "Moderate"

    def test_elevated_vix(self):
        assert _vix_label(35) == "Elevated"

    def test_none_vix_returns_dash(self):
        assert _vix_label(None) == "—"


# ── _format_message ──────────────────────────────────────────��───────────────

class TestFormatMessage:
    def test_header_contains_signaldesk(self):
        msg = _format_message(MULTI_RESULTS)
        assert "📊 SignalDesk" in msg

    def test_all_tickers_present(self):
        msg = _format_message(MULTI_RESULTS)
        assert "AAPL" in msg
        assert "BTC-USD" in msg
        assert "TSLA" in msg

    def test_tickers_sorted_by_score_descending(self):
        msg = _format_message(MULTI_RESULTS)
        pos_aapl = msg.index("AAPL")      # score 72 — should be first
        pos_tsla = msg.index("TSLA")      # score 55 — should be second
        pos_btc  = msg.index("BTC-USD")   # score 38 — should be last
        assert pos_aapl < pos_tsla < pos_btc

    def test_top_signal_shows_highest_score_ticker(self):
        msg = _format_message(MULTI_RESULTS)
        assert "Top signal: AAPL" in msg

    def test_top_signal_includes_suggested_action(self):
        msg = _format_message(MULTI_RESULTS)
        assert "Buy dips" in msg

    def test_macro_vix_present(self):
        msg = _format_message(MULTI_RESULTS)
        assert "VIX 18.5" in msg

    def test_macro_10y_present(self):
        msg = _format_message(MULTI_RESULTS)
        assert "10Y 4.2%" in msg

    def test_vix_label_in_macro(self):
        msg = _format_message(MULTI_RESULTS)
        assert "Low Fear" in msg

    def test_dashboard_url_present(self):
        msg = _format_message(MULTI_RESULTS)
        assert "http://localhost:8088" in msg

    def test_bull_emoji_for_high_score(self):
        msg = _format_message(MULTI_RESULTS)
        assert "🟢" in msg

    def test_bear_emoji_for_low_score(self):
        msg = _format_message(MULTI_RESULTS)
        assert "🔴" in msg

    def test_neutral_emoji_for_mid_score(self):
        msg = _format_message(MULTI_RESULTS)
        assert "⚪" in msg

    def test_single_ticker_no_crash(self):
        msg = _format_message([make_result("NVDA", 70)])
        assert "NVDA" in msg
        assert "Top signal: NVDA" in msg

    def test_missing_vix_shows_dash(self):
        r = make_result("AAPL", 70)
        r["macro"].pop("vix")
        msg = _format_message([r])
        assert "VIX —" in msg

    def test_missing_us10y_shows_dash(self):
        r = make_result("AAPL", 70)
        r["macro"].pop("us10y")
        msg = _format_message([r])
        assert "10Y —" in msg

    def test_no_suggested_action_still_formats(self):
        r = make_result("AAPL", 70)
        r["analysis"].pop("suggested_action")
        msg = _format_message([r])
        assert "Top signal: AAPL" in msg


# ── _build_discord_payload ───────────────────────────────────────────────────

class TestBuildDiscordPayload:
    def test_embed_has_all_tickers(self):
        payload = _build_discord_payload(DISCORD_RESULTS)
        names = [f["name"] for f in payload["embeds"][0]["fields"]]
        assert set(names) == {"AAPL", "NVDA", "TSLA", "BTC-USD", "EURUSD=X"}

    def test_tickers_sorted_by_score_descending(self):
        payload = _build_discord_payload(DISCORD_RESULTS)
        fields = payload["embeds"][0]["fields"]
        scores = []
        for f in fields:
            score_str = f["value"].split("/100")[0].split()[-1]
            scores.append(int(score_str))
        assert scores == sorted(scores, reverse=True)

    def test_color_green_when_majority_bullish(self):
        bullish_results = [
            make_result("AAPL", 72), make_result("NVDA", 65),
            make_result("X", 80), make_result("BTC-USD", 38),
        ]
        payload = _build_discord_payload(bullish_results)
        assert payload["embeds"][0]["color"] == 0x00D17A

    def test_color_red_when_majority_bearish(self):
        bearish_results = [
            make_result("AAPL", 30), make_result("NVDA", 25),
            make_result("TSLA", 35), make_result("X", 70),
        ]
        payload = _build_discord_payload(bearish_results)
        assert payload["embeds"][0]["color"] == 0xFF4D6D

    def test_color_grey_when_mixed(self):
        mixed_results = [
            make_result("AAPL", 70), make_result("BTC-USD", 30),
        ]
        payload = _build_discord_payload(mixed_results)
        assert payload["embeds"][0]["color"] == 0x7A8494

    def test_footer_contains_vix_and_10y(self):
        payload = _build_discord_payload(DISCORD_RESULTS)
        footer = payload["embeds"][0]["footer"]["text"]
        assert "VIX 18.5" in footer
        assert "10Y 4.2%" in footer

    def test_footer_contains_vix_label(self):
        payload = _build_discord_payload(DISCORD_RESULTS)
        footer = payload["embeds"][0]["footer"]["text"]
        assert "Low Fear" in footer

    def test_footer_contains_macro_score(self):
        payload = _build_discord_payload(DISCORD_RESULTS)
        footer = payload["embeds"][0]["footer"]["text"]
        assert "Macro 62/100" in footer

    def test_timestamp_present(self):
        payload = _build_discord_payload(DISCORD_RESULTS)
        assert "timestamp" in payload["embeds"][0]

    def test_title_contains_signaldesk(self):
        payload = _build_discord_payload(DISCORD_RESULTS)
        assert "SignalDesk" in payload["embeds"][0]["title"]

    def test_fields_are_inline(self):
        payload = _build_discord_payload(DISCORD_RESULTS)
        for field in payload["embeds"][0]["fields"]:
            assert field["inline"] is True

    def test_suggested_action_truncated_to_80_chars(self):
        long_action = "A" * 120
        results = [make_result("AAPL", 70, suggested_action=long_action)]
        payload = _build_discord_payload(results)
        value = payload["embeds"][0]["fields"][0]["value"]
        action_line = value.split("\n")[1]
        assert len(action_line) <= 80

    def test_missing_suggested_action_still_formats(self):
        r = make_result("AAPL", 70)
        r["analysis"].pop("suggested_action")
        payload = _build_discord_payload([r])
        value = payload["embeds"][0]["fields"][0]["value"]
        assert "70/100" in value

    def test_missing_vix_shows_dash_in_footer(self):
        r = make_result("AAPL", 70, vix=None)
        payload = _build_discord_payload([r])
        footer = payload["embeds"][0]["footer"]["text"]
        assert "VIX —" in footer

    def test_missing_us10y_shows_dash_in_footer(self):
        r = make_result("AAPL", 70, us10y=None)
        payload = _build_discord_payload([r])
        footer = payload["embeds"][0]["footer"]["text"]
        assert "10Y —" in footer

    def test_single_ticker_no_crash(self):
        payload = _build_discord_payload([make_result("NVDA", 70)])
        assert len(payload["embeds"][0]["fields"]) == 1
        assert payload["embeds"][0]["fields"][0]["name"] == "NVDA"


# ── send_discord_summary ─────────────────────────────────────────────────────

class TestSendDiscordSummary:
    def test_skips_when_webhook_not_configured(self, caplog):
        keys = {"discord_webhook": "YOUR_DISCORD_WEBHOOK_URL"}
        with patch("pipeline.config.API_KEYS", keys):
            with caplog.at_level(logging.WARNING, logger="pipeline.notifier"):
                send_discord_summary(MULTI_RESULTS)
        assert any("not configured" in r.message for r in caplog.records)

    def test_skips_when_webhook_empty(self, caplog):
        keys = {"discord_webhook": ""}
        with patch("pipeline.config.API_KEYS", keys):
            with caplog.at_level(logging.WARNING, logger="pipeline.notifier"):
                send_discord_summary(MULTI_RESULTS)
        assert any("not configured" in r.message for r in caplog.records)

    def test_skips_when_webhook_missing(self, caplog):
        with patch("pipeline.config.API_KEYS", {}):
            with caplog.at_level(logging.WARNING, logger="pipeline.notifier"):
                send_discord_summary(MULTI_RESULTS)
        assert any("not configured" in r.message for r in caplog.records)

    def test_skips_when_results_empty(self, caplog):
        with patch("pipeline.config.API_KEYS", VALID_KEYS):
            with caplog.at_level(logging.WARNING, logger="pipeline.notifier"):
                send_discord_summary([])
        assert any("No pipeline results" in r.message for r in caplog.records)

    def test_sends_when_configured(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("pipeline.config.API_KEYS", VALID_KEYS), \
             patch("pipeline.notifier.requests.post", return_value=mock_resp) as mock_post:
            send_discord_summary(MULTI_RESULTS)
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == VALID_KEYS["discord_webhook"]
        assert "embeds" in call_args[1]["json"]

    def test_skips_gracefully_when_post_raises(self, caplog):
        with patch("pipeline.config.API_KEYS", VALID_KEYS), \
             patch("pipeline.notifier.requests.post", side_effect=Exception("Connection refused")):
            with caplog.at_level(logging.WARNING, logger="pipeline.notifier"):
                send_discord_summary(MULTI_RESULTS)
        assert any("Discord notification failed" in r.message for r in caplog.records)

    def test_pipeline_does_not_crash_on_discord_exception(self):
        with patch("pipeline.config.API_KEYS", VALID_KEYS), \
             patch("pipeline.notifier.requests.post", side_effect=RuntimeError("timeout")):
            send_discord_summary(MULTI_RESULTS)  # must not raise
