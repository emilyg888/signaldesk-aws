"""
Unit tests — pipeline/config.py, social_fetcher.py, sentiment.py, ai_analyst.py
Uses mocking to avoid OpenAI / API calls.
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Config tests ──────────────────────────────────────────────────────────────

class TestConfig:

    def test_default_watchlist_is_list(self):
        from pipeline.config import DEFAULT_WATCHLIST
        assert isinstance(DEFAULT_WATCHLIST, list)
        assert len(DEFAULT_WATCHLIST) > 0

    def test_weights_sum_to_one(self):
        from pipeline.config import SETTINGS
        weights = SETTINGS["weights"]
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"

    def test_openai_has_required_keys(self):
        from pipeline.config import OPENAI
        for key in ["api_key", "analysis_model", "sentiment_model", "content_model", "temperature", "max_tokens"]:
            assert key in OPENAI, f"Missing OPENAI key: {key}"

    def test_api_keys_has_required_keys(self):
        from pipeline.config import API_KEYS
        for key in ["fred", "newsapi"]:
            assert key in API_KEYS, f"Missing API_KEY: {key}"

    def test_paths_has_required_keys(self):
        from pipeline.config import PATHS
        for key in ["db", "cache", "logs"]:
            assert key in PATHS, f"Missing PATH: {key}"

    def test_load_watchlist_creates_default(self, tmp_path, monkeypatch):
        from pipeline import config
        monkeypatch.setattr(config, "WATCHLIST_FILE", tmp_path / "watchlist.json")
        wl = config.load_watchlist()
        assert isinstance(wl, list)
        assert len(wl) > 0

    def test_save_and_load_watchlist(self, tmp_path, monkeypatch):
        from pipeline import config
        monkeypatch.setattr(config, "WATCHLIST_FILE", tmp_path / "watchlist.json")
        tickers = ["AAPL", "TSLA", "BTC-USD"]
        config.save_watchlist(tickers)
        loaded = config.load_watchlist()
        assert loaded == tickers

    def test_temperature_in_valid_range(self):
        from pipeline.config import OPENAI
        assert 0.0 <= OPENAI["temperature"] <= 1.0

    def test_max_tokens_positive(self):
        from pipeline.config import OPENAI
        assert OPENAI["max_tokens"] > 0

    def test_lookback_days_sufficient_for_ema50(self):
        from pipeline.config import SETTINGS
        assert SETTINGS["lookback_days"] >= 50, \
            "lookback_days must be >=50 for EMA50 to compute"


# ── Social fetcher tests ──────────────────────────────────────────────────────

class TestSocialFetcher:

    def test_returns_empty_list_when_no_token(self, monkeypatch):
        from pipeline import social_fetcher
        from pipeline.config import API_KEYS
        monkeypatch.setitem(API_KEYS, "x_bearer_token", "YOUR_X_BEARER_TOKEN")
        from pipeline.social_fetcher import fetch_social
        result = fetch_social("AAPL")
        assert result == []

    def test_returns_list_type(self):
        from pipeline.social_fetcher import fetch_social
        with patch("pipeline.social_fetcher.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"data": [], "includes": {}}
            result = fetch_social("BTC-USD")
        assert isinstance(result, list)

    def test_handles_any_ticker(self):
        from pipeline.social_fetcher import fetch_social
        with patch("pipeline.social_fetcher.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"data": [], "includes": {}}
            for ticker in ["AAPL", "BTC-USD", "EURUSD=X", "UNKNOWN"]:
                result = fetch_social(ticker)
                assert isinstance(result, list)

    def test_returns_posts_when_api_succeeds(self):
        from pipeline.social_fetcher import fetch_social
        mock_data = {
            "data": [{"id": "123", "text": "$AAPL bullish setup", "author_id": "u1",
                      "created_at": "2026-01-01T09:00:00Z",
                      "public_metrics": {"like_count": 10, "retweet_count": 2,
                                         "reply_count": 1, "quote_count": 0}}],
            "includes": {"users": [{"id": "u1", "verified": False,
                                    "public_metrics": {"followers_count": 5000}}]}
        }
        with patch("pipeline.social_fetcher.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_data
            result = fetch_social("AAPL")
        assert len(result) == 1
        assert result[0]["title"] == "$AAPL bullish setup"

    def test_rate_limit_returns_empty(self):
        from pipeline.social_fetcher import fetch_social
        with patch("pipeline.social_fetcher.requests.get") as mock_get:
            mock_get.return_value.status_code = 429
            result = fetch_social("AAPL")
        assert result == []

    def test_api_error_returns_empty(self):
        from pipeline.social_fetcher import fetch_social
        with patch("pipeline.social_fetcher.requests.get") as mock_get:
            mock_get.side_effect = Exception("connection error")
            result = fetch_social("AAPL")
        assert result == []


# ── Sentiment tests ───────────────────────────────────────────────────────────

class TestSentiment:

    def _make_mock_response(self, score=65, label="Bullish", themes=None):
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = json.dumps({
            "score": score,
            "label": label,
            "key_themes": themes or ["AI", "earnings"],
        })
        return mock_resp

    def test_empty_news_returns_neutral(self):
        from pipeline.sentiment import score_sentiment
        result = score_sentiment([], [], "AAPL")
        assert result["composite_score"] == 50
        assert result["label"] == "Neutral"

    def test_bullish_score_returns_bullish_label(self):
        from pipeline.sentiment import score_sentiment
        with patch("pipeline.sentiment.client") as mock_client:
            mock_client.chat.completions.create.return_value = \
                self._make_mock_response(score=75, label="Bullish")
            news = [{"headline": "Apple beats earnings"}]
            result = score_sentiment(news, [], "AAPL")
        assert result["composite_score"] >= 60
        assert result["label"] == "Bullish"

    def test_bearish_score_returns_bearish_label(self):
        from pipeline.sentiment import score_sentiment
        with patch("pipeline.sentiment.client") as mock_client:
            mock_client.chat.completions.create.return_value = \
                self._make_mock_response(score=25, label="Bearish")
            news = [{"headline": "Apple misses revenue targets"}]
            result = score_sentiment(news, [], "AAPL")
        assert result["composite_score"] <= 40
        assert result["label"] == "Bearish"

    def test_result_has_required_keys(self):
        from pipeline.sentiment import score_sentiment
        with patch("pipeline.sentiment.client") as mock_client:
            mock_client.chat.completions.create.return_value = \
                self._make_mock_response()
            result = score_sentiment([{"headline": "test"}], [], "AAPL")
        for key in ["composite_score", "label", "sources", "key_themes"]:
            assert key in result

    def test_composite_score_in_range(self):
        from pipeline.sentiment import score_sentiment
        with patch("pipeline.sentiment.client") as mock_client:
            mock_client.chat.completions.create.return_value = \
                self._make_mock_response(score=70)
            result = score_sentiment([{"headline": "test"}], [], "AAPL")
        assert 0 <= result["composite_score"] <= 100

    def test_json_decode_error_returns_neutral(self):
        from pipeline.sentiment import score_sentiment
        with patch("pipeline.sentiment.client") as mock_client:
            bad_resp = MagicMock()
            bad_resp.choices[0].message.content = "not valid json at all"
            mock_client.chat.completions.create.return_value = bad_resp
            result = score_sentiment([{"headline": "test"}], [], "AAPL")
        assert result["composite_score"] == 50

    def test_openai_exception_returns_neutral(self):
        from pipeline.sentiment import score_sentiment
        with patch("pipeline.sentiment.client") as mock_client:
            mock_client.chat.completions.create.side_effect = Exception("connection refused")
            result = score_sentiment([{"headline": "test"}], [], "AAPL")
        assert result["composite_score"] == 50

    def test_key_themes_returned(self):
        from pipeline.sentiment import score_sentiment
        with patch("pipeline.sentiment.client") as mock_client:
            mock_client.chat.completions.create.return_value = \
                self._make_mock_response(themes=["AI boom", "rate cuts"])
            result = score_sentiment([{"headline": "test"}], [], "AAPL")
        assert "AI boom" in result["key_themes"]

    def test_social_posts_ignored_gracefully(self):
        """social_posts param accepted but not used — no crash."""
        from pipeline.sentiment import score_sentiment
        social = [{"title": "moon", "score": 10}]
        result = score_sentiment([], social, "AAPL")
        assert isinstance(result, dict)


# ── AI Analyst tests ──────────────────────────────────────────────────────────

class TestAiAnalyst:

    def _make_valid_analysis(self):
        return {
            "bias": "Bullish",
            "conviction": "High",
            "narrative": "Strong momentum with positive sentiment.",
            "key_risks": ["Fed hawkishness"],
            "key_catalysts": ["Earnings beat"],
            "forecast": [
                {"day": f"D+{i}", "direction": "Up", "magnitude": "+0.8%", "confidence": 65}
                for i in range(1, 6)
            ],
            "key_levels": {"support": ["185"], "resistance": ["195"]},
            "suggested_action": "Watch for breakout above 195.",
        }

    def _make_inputs(self):
        price_data  = {"current_price": 190.0, "change_pct": 1.2}
        technicals  = {"rsi": 58, "macd": 0.5, "macd_signal": 0.3, "macd_hist": 0.2,
                       "ema20": 188.0, "ema50": 185.0, "ema_cross": "bullish",
                       "bb_position": "mid", "bb_width": 0.05,
                       "atr_pct": 1.2, "volume_ratio": 1.3,
                       "stoch_k": 62, "stoch_d": 58, "composite_score": 65}
        sentiment   = {"composite_score": 68, "label": "Bullish",
                       "sources": {"news": {"score": 68, "label": "Bullish"}},
                       "key_themes": ["AI", "earnings"]}
        macro       = {"vix": 16, "dxy": 104, "us10y": 4.3, "fed_rate": 5.25,
                       "cpi_yoy": 3.1, "gdp_qoq": 2.4, "sp500": 5200, "gold": 2300,
                       "composite_score": 55}
        return price_data, technicals, sentiment, macro

    def test_valid_response_parsed(self):
        from pipeline.ai_analyst import generate_analysis
        price_data, technicals, sentiment, macro = self._make_inputs()
        with patch("pipeline.ai_analyst.client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = json.dumps(self._make_valid_analysis())
            mock_client.chat.completions.create.return_value = mock_resp
            result = generate_analysis("AAPL", price_data, technicals, sentiment, macro)
        assert result["bias"] == "Bullish"
        assert result["conviction"] == "High"
        assert len(result["forecast"]) == 5

    def test_required_keys_present(self):
        from pipeline.ai_analyst import generate_analysis
        price_data, technicals, sentiment, macro = self._make_inputs()
        with patch("pipeline.ai_analyst.client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = json.dumps(self._make_valid_analysis())
            mock_client.chat.completions.create.return_value = mock_resp
            result = generate_analysis("AAPL", price_data, technicals, sentiment, macro)
        for key in ["bias", "conviction", "narrative", "key_risks",
                    "key_catalysts", "forecast", "key_levels", "suggested_action"]:
            assert key in result, f"Missing key: {key}"

    def test_json_decode_error_returns_fallback(self):
        from pipeline.ai_analyst import generate_analysis
        price_data, technicals, sentiment, macro = self._make_inputs()
        with patch("pipeline.ai_analyst.client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = "not json"
            mock_client.chat.completions.create.return_value = mock_resp
            result = generate_analysis("AAPL", price_data, technicals, sentiment, macro)
        assert "bias" in result
        assert result["conviction"] == "Low"

    def test_exception_returns_fallback(self):
        from pipeline.ai_analyst import generate_analysis
        price_data, technicals, sentiment, macro = self._make_inputs()
        with patch("pipeline.ai_analyst.client") as mock_client:
            mock_client.chat.completions.create.side_effect = Exception("timeout")
            result = generate_analysis("AAPL", price_data, technicals, sentiment, macro)
        assert "bias" in result
        assert len(result["forecast"]) == 5

    def test_forecast_has_5_days(self):
        from pipeline.ai_analyst import generate_analysis
        price_data, technicals, sentiment, macro = self._make_inputs()
        with patch("pipeline.ai_analyst.client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = json.dumps(self._make_valid_analysis())
            mock_client.chat.completions.create.return_value = mock_resp
            result = generate_analysis("AAPL", price_data, technicals, sentiment, macro)
        assert len(result["forecast"]) == 5

    def test_markdown_fences_stripped(self):
        from pipeline.ai_analyst import generate_analysis
        price_data, technicals, sentiment, macro = self._make_inputs()
        with patch("pipeline.ai_analyst.client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = (
                "```json\n" + json.dumps(self._make_valid_analysis()) + "\n```"
            )
            mock_client.chat.completions.create.return_value = mock_resp
            result = generate_analysis("AAPL", price_data, technicals, sentiment, macro)
        assert result["bias"] == "Bullish"

    def test_partial_analysis_response_gets_normalized(self):
        from pipeline.ai_analyst import generate_analysis
        price_data, technicals, sentiment, macro = self._make_inputs()
        partial = {
            "bias": "Bullish",
            "narrative": "Momentum remains constructive.",
            "forecast": [{"day": "D+1", "direction": "Up", "magnitude": "+0.5%", "confidence": 64}],
        }
        with patch("pipeline.ai_analyst.client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = json.dumps(partial)
            mock_client.chat.completions.create.return_value = mock_resp
            result = generate_analysis("AAPL", price_data, technicals, sentiment, macro)
        assert result["conviction"] == "Low"
        assert len(result["forecast"]) == 5
        assert result["forecast"][0]["day"] == "D+1"
        assert result["forecast"][1]["day"] == "D+2"
        assert "support" in result["key_levels"]

    def test_build_prompt_no_reddit_key(self):
        """Ensure _build_prompt doesn't crash without reddit in sentiment sources."""
        from pipeline.ai_analyst import _build_prompt
        price_data, technicals, sentiment, macro = self._make_inputs()
        # sentiment has only 'news' source — no 'reddit'
        prompt = _build_prompt("AAPL", price_data, technicals, sentiment, macro)
        assert "AAPL" in prompt
        assert "TECHNICAL" in prompt
        assert "SENTIMENT" in prompt
        assert "MACRO" in prompt

    def test_generate_earnings_story_normalizes_response(self):
        from pipeline.ai_analyst import generate_earnings_story
        price_data, technicals, sentiment, macro = self._make_inputs()
        run_data = {
            "ticker": "AAPL",
            "price_data": price_data,
            "technicals": technicals,
            "sentiment": sentiment,
            "macro": macro,
            "analysis": self._make_valid_analysis(),
            "aggregate_score": 66,
            "news": [{"headline": "Apple earnings expected"}],
        }
        payload = {
            "headline": "Apple Earnings Story",
            "dek": "Apple shares rose after the latest signal run.",
            "body": ["Paragraph one."],
            "latest_earnings_report": {
                "report_date": "2026-05-01",
                "summary": "Apple reported quarterly revenue growth.",
                "source_links": [{"title": "Apple report", "url": "https://example.com/apple"}],
            },
            "watch_items": ["Guidance"],
            "disclosure_note": "Draft only.",
        }
        with patch("pipeline.ai_analyst.client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = json.dumps(payload)
            mock_client.chat.completions.create.return_value = mock_resp
            result = generate_earnings_story("AAPL", run_data)
        assert result["headline"] == "Apple Earnings Story"
        assert result["body"] == ["Paragraph one."]
        assert result["latest_earnings_report"]["report_date"] == "2026-05-01"
        assert result["latest_earnings_report"]["source_links"][0]["url"] == "https://example.com/apple"

    def test_generate_earnings_story_fallback_includes_report_date(self):
        from pipeline.ai_analyst import generate_earnings_story
        price_data, technicals, sentiment, macro = self._make_inputs()
        run_data = {
            "ticker": "AAPL",
            "price_data": price_data,
            "technicals": technicals,
            "sentiment": sentiment,
            "macro": macro,
            "analysis": self._make_valid_analysis(),
            "aggregate_score": 66,
            "news": [{
                "headline": "Apple posts quarterly earnings beat",
                "source": "Example News",
                "url": "https://example.com/earnings",
                "published_at": "2026-05-02T12:00:00Z",
            }],
        }
        with patch("pipeline.ai_analyst.client") as mock_client:
            mock_client.chat.completions.create.side_effect = Exception("timeout")
            result = generate_earnings_story("AAPL", run_data)
        report = result["latest_earnings_report"]
        assert report["report_date"] == "2026-05-02"
        assert report["source_links"][0]["url"] == "https://example.com/earnings"

    def test_generate_news_draft_returns_fallback_on_error(self):
        from pipeline.ai_analyst import generate_news_draft
        price_data, technicals, sentiment, macro = self._make_inputs()
        run_data = {
            "ticker": "AAPL",
            "price_data": price_data,
            "technicals": technicals,
            "sentiment": sentiment,
            "macro": macro,
            "analysis": self._make_valid_analysis(),
            "aggregate_score": 66,
            "news": [],
        }
        with patch("pipeline.ai_analyst.client") as mock_client:
            mock_client.chat.completions.create.side_effect = Exception("timeout")
            result = generate_news_draft("AAPL", run_data)
        assert "headline" in result
        assert "editor_checks" in result


# ── Additional sentiment tests for X source blending ─────────────────────────

class TestSentimentXBlending:

    def _make_mock_response(self, score=65, label="Bullish", themes=None):
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = json.dumps({
            "score": score, "label": label,
            "key_themes": themes or ["AI", "earnings"],
        })
        return mock_resp

    def test_x_posts_blended_when_available(self):
        from pipeline.sentiment import score_sentiment
        social = [{"title": "BTC mooning right now!!"}]
        with patch("pipeline.sentiment.client") as mock_client:
            mock_client.chat.completions.create.return_value = \
                self._make_mock_response(score=70)
            result = score_sentiment(
                [{"headline": "Bitcoin rally continues"}],
                social,
                "BTC-USD"
            )
        assert result["sources"]["x"] is not None

    def test_x_source_is_none_when_no_posts(self):
        from pipeline.sentiment import score_sentiment
        with patch("pipeline.sentiment.client") as mock_client:
            mock_client.chat.completions.create.return_value = \
                self._make_mock_response(score=60)
            result = score_sentiment([{"headline": "test"}], [], "AAPL")
        assert result["sources"]["x"] is None

    def test_no_sources_returns_neutral(self):
        from pipeline.sentiment import score_sentiment
        result = score_sentiment([], [], "AAPL")
        assert result["composite_score"] == 50
        assert result["label"] == "Neutral"

    def test_themes_merged_from_both_sources(self):
        from pipeline.sentiment import score_sentiment
        social = [{"title": "crypto pump incoming"}]
        with patch("pipeline.sentiment.client") as mock_client:
            mock_client.chat.completions.create.side_effect = [
                self._make_mock_response(score=65, themes=["momentum", "AI"]),
                self._make_mock_response(score=70, themes=["FOMO", "rally"]),
            ]
            result = score_sentiment(
                [{"headline": "test news"}], social, "BTC-USD"
            )
        assert len(result["key_themes"]) > 0

    def test_x_only_sentiment_works(self):
        from pipeline.sentiment import score_sentiment
        social = [{"title": "NVDA to the moon"}]
        with patch("pipeline.sentiment.client") as mock_client:
            mock_client.chat.completions.create.return_value = \
                self._make_mock_response(score=75)
            result = score_sentiment([], social, "NVDA")
        assert result["composite_score"] == 75
