"""
System Integration Tests (SIT) — pipeline/run_pipeline.py
Tests the full pipeline end-to-end with mocked external calls.
Verifies all modules work together correctly.
No real API calls, no real OpenAI calls, no file system side effects.
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Shared fixtures ───────────────────────────────────────────────────────────

def make_price_history(n=60, base=190.0):
    import pandas as pd
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return [
        {
            "date":   d.strftime("%Y-%m-%d"),
            "open":   round(base - 0.2, 4),
            "high":   round(base + 0.5, 4),
            "low":    round(base - 0.5, 4),
            "close":  round(base + i * 0.01, 4),
            "volume": 1_000_000,
        }
        for i, d in enumerate(dates)
    ]


def mock_price_data(ticker="AAPL"):
    return {
        "ticker":        ticker,
        "symbol":        ticker,
        "current_price": 190.42,
        "prev_close":    188.90,
        "change":        1.52,
        "change_pct":    0.80,
        "history":       make_price_history(),
        "fetched_at":    datetime.now().isoformat(),
    }


def mock_macro():
    return {
        "vix": 16.8, "dxy": 104.2, "us10y": 4.38,
        "sp500": 5200.0, "gold": 2300.0,
        "fed_rate": 5.25, "cpi_yoy": 3.2, "gdp_qoq": 2.4,
        "composite_score": 55,
    }


def mock_news():
    return [
        {"headline": "Apple beats Q1 earnings expectations", "source": "Bloomberg",
         "url": "https://example.com/1", "published_at": "2025-01-01T08:00:00", "summary": ""},
        {"headline": "iPhone sales strong in emerging markets", "source": "Reuters",
         "url": "https://example.com/2", "published_at": "2025-01-01T07:00:00", "summary": ""},
    ]


def mock_sentiment_response(score=68):
    resp = MagicMock()
    resp.choices[0].message.content = json.dumps({
        "score": score, "label": "Bullish", "key_themes": ["earnings", "AI"],
    })
    return resp


def mock_analysis_response():
    resp = MagicMock()
    resp.choices[0].message.content = json.dumps({
        "bias": "Bullish",
        "conviction": "Medium",
        "narrative": "Technical momentum aligns with positive sentiment.",
        "key_risks": ["Fed policy", "China demand"],
        "key_catalysts": ["Earnings beat", "AI integration"],
        "forecast": [
            {"day": f"D+{i}", "direction": "Up", "magnitude": "+0.6%", "confidence": 64}
            for i in range(1, 6)
        ],
        "key_levels": {"support": ["185.00", "182.50"], "resistance": ["195.00", "200.00"]},
        "suggested_action": "Hold long, watch 195 resistance.",
    })
    return resp


@pytest.fixture
def mock_lm_studio():
    """Mock OpenAI client — returns valid JSON for both calls."""
    with patch("pipeline.sentiment.client") as sent_client, \
         patch("pipeline.ai_analyst.client") as anal_client:
        sent_client.chat.completions.create.return_value = mock_sentiment_response()
        anal_client.chat.completions.create.return_value = mock_analysis_response()
        yield sent_client, anal_client


@pytest.fixture
def mock_external_data():
    """Mock all external data fetches."""
    with patch("pipeline.run_pipeline.fetch_price_data") as mock_price, \
         patch("pipeline.run_pipeline.fetch_macro_data") as mock_macro_fn, \
         patch("pipeline.run_pipeline.fetch_news") as mock_news_fn:
        mock_price.side_effect = lambda ticker: mock_price_data(ticker)
        mock_macro_fn.return_value = mock_macro()
        mock_news_fn.return_value = mock_news()
        yield mock_price, mock_macro_fn, mock_news_fn


# ── SIT: process_ticker() ─────────────────────────────────────────────────────

class TestProcessTicker:

    def test_returns_complete_result(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        assert result["ticker"] == "AAPL"

    def test_result_has_all_required_keys(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        required = ["ticker", "run_date", "price_data", "technicals",
                    "sentiment", "macro", "news", "social", "analysis", "aggregate_score"]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_aggregate_score_in_range(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        assert 0 <= result["aggregate_score"] <= 100

    def test_aggregate_score_uses_weights(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        """Verify aggregate = 40% tech + 35% sent + 25% macro."""
        import pipeline.storage as storage
        from pipeline.config import SETTINGS
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        tech  = result["technicals"]["composite_score"]
        sent  = result["sentiment"]["composite_score"]
        macro = result["macro"]["composite_score"]
        w = SETTINGS["weights"]
        expected = round(tech * w["technical"] + sent * w["sentiment"] + macro * w["macro"])
        assert result["aggregate_score"] == expected

    def test_price_data_populated(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        assert result["price_data"]["current_price"] == 190.42
        assert result["price_data"]["change_pct"] == 0.80

    def test_technicals_computed(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        assert result["technicals"]["rsi"] is not None
        assert "composite_score" in result["technicals"]

    def test_sentiment_scored(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        assert "composite_score" in result["sentiment"]
        assert result["sentiment"]["composite_score"] == 68

    def test_analysis_generated(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        assert result["analysis"]["bias"] == "Bullish"
        assert len(result["analysis"]["forecast"]) == 5

    def test_social_posts_is_list(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        assert isinstance(result["social"], list)


# ── SIT: full run() with multiple tickers ─────────────────────────────────────

class TestFullRun:

    def test_processes_all_tickers(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        from pipeline import config
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        monkeypatch.setattr(config, "WATCHLIST_FILE", tmp_path / "watchlist.json")
        config.save_watchlist(["AAPL", "NVDA", "TSLA"])
        storage.init_db()
        from pipeline.run_pipeline import run
        results = run()
        assert len(results) == 3

    def test_results_saved_to_db(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        from pipeline import config
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        monkeypatch.setattr(config, "WATCHLIST_FILE", tmp_path / "watchlist.json")
        config.save_watchlist(["AAPL", "NVDA"])
        storage.init_db()
        from pipeline.run_pipeline import run
        run()
        all_results = storage.get_all_latest()
        assert len(all_results) == 2

    def test_ticker_failure_doesnt_stop_pipeline(self, tmp_path, monkeypatch):
        """If one ticker fails, others should still process."""
        import pipeline.storage as storage
        from pipeline import config
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        monkeypatch.setattr(config, "WATCHLIST_FILE", tmp_path / "watchlist.json")
        config.save_watchlist(["AAPL", "BADTICKER", "NVDA"])
        storage.init_db()

        call_count = {"n": 0}
        def side_effect(ticker):
            call_count["n"] += 1
            if ticker == "BADTICKER":
                raise ValueError("Simulated fetch failure")
            return mock_price_data(ticker)

        with patch("pipeline.run_pipeline.fetch_price_data", side_effect=side_effect), \
             patch("pipeline.run_pipeline.fetch_macro_data", return_value=mock_macro()), \
             patch("pipeline.run_pipeline.fetch_news", return_value=mock_news()), \
             patch("pipeline.sentiment.client") as sc, \
             patch("pipeline.ai_analyst.client") as ac:
            sc.chat.completions.create.return_value = mock_sentiment_response()
            ac.chat.completions.create.return_value = mock_analysis_response()
            from pipeline.run_pipeline import run
            results = run()

        # AAPL and NVDA should succeed; BADTICKER fails gracefully
        assert len(results) == 2
        tickers = [r["ticker"] for r in results]
        assert "AAPL" in tickers
        assert "NVDA" in tickers
        assert "BADTICKER" not in tickers

    def test_all_tickers_correct_scores(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        from pipeline import config
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        monkeypatch.setattr(config, "WATCHLIST_FILE", tmp_path / "watchlist.json")
        config.save_watchlist(["AAPL", "TSLA"])
        storage.init_db()
        from pipeline.run_pipeline import run
        results = run()
        for r in results:
            assert 0 <= r["aggregate_score"] <= 100

    def test_empty_watchlist_returns_empty(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        from pipeline import config
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        monkeypatch.setattr(config, "WATCHLIST_FILE", tmp_path / "watchlist.json")
        config.save_watchlist([])
        storage.init_db()
        from pipeline.run_pipeline import run
        results = run()
        assert results == []


# ── SIT: data flow integrity ──────────────────────────────────────────────────

class TestDataFlowIntegrity:

    def test_ticker_preserved_through_pipeline(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("BTC-USD")
        assert result["ticker"] == "BTC-USD"

    def test_run_date_is_valid_iso(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        # Should parse as valid datetime
        dt = datetime.fromisoformat(result["run_date"])
        assert dt.year >= 2025

    def test_saved_result_retrievable(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        from pipeline.run_pipeline import process_ticker
        storage.init_db()
        result = process_ticker("AAPL")
        storage.save_run(result)
        retrieved = storage.get_latest_run("AAPL")
        assert retrieved is not None
        assert retrieved["ticker"] == "AAPL"
        assert retrieved["aggregate_score"] == result["aggregate_score"]

    def test_history_queryable_after_run(self, mock_external_data, mock_lm_studio, tmp_path, monkeypatch):
        import pipeline.storage as storage
        from pipeline import config
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        monkeypatch.setattr(config, "WATCHLIST_FILE", tmp_path / "watchlist.json")
        config.save_watchlist(["AAPL"])
        storage.init_db()
        from pipeline.run_pipeline import run
        run()
        history = storage.get_history("AAPL")
        assert len(history) >= 1
        assert history[0]["agg_score"] is not None
