"""
Unit tests — pipeline/technical.py
Tests: compute_technicals(), _tech_score()
Uses synthetic price data — no external API calls.
"""

import sys
import math
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.technical import compute_technicals, _tech_score


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_price_data(n=60, start=100.0, trend=0.0, noise=0.5) -> dict:
    """Generate synthetic OHLCV price_data dict."""
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    closes = [start + trend * i + noise * (i % 3 - 1) for i in range(n)]
    history = []
    for i, (date, close) in enumerate(zip(dates, closes)):
        history.append({
            "date":   date.strftime("%Y-%m-%d"),
            "open":   round(close - 0.2, 4),
            "high":   round(close + 0.5, 4),
            "low":    round(close - 0.5, 4),
            "close":  round(close, 4),
            "volume": 1_000_000 + i * 10_000,
        })
    return {"history": history, "ticker": "TEST", "symbol": "TEST"}


def make_bullish_data(n=60) -> dict:
    """Strong uptrend — should produce high tech score."""
    return make_price_data(n=n, start=100.0, trend=0.5, noise=0.1)


def make_bearish_data(n=60) -> dict:
    """Strong downtrend — should produce low tech score."""
    return make_price_data(n=n, start=130.0, trend=-0.5, noise=0.1)


def make_flat_data(n=60) -> dict:
    """Flat/sideways — should produce neutral score ~50."""
    return make_price_data(n=n, start=100.0, trend=0.0, noise=0.3)


# ── Unit tests: compute_technicals() ─────────────────────────────────────────

class TestComputeTechnicals:

    def test_returns_dict(self):
        result = compute_technicals(make_price_data())
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        result = compute_technicals(make_price_data())
        required = [
            "rsi", "macd", "macd_signal", "macd_hist",
            "ema20", "ema_cross", "bb_position",
            "volume_ratio", "composite_score",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_rsi_in_range(self):
        result = compute_technicals(make_price_data())
        assert result["rsi"] is not None
        assert 0 <= result["rsi"] <= 100, f"RSI out of range: {result['rsi']}"

    def test_composite_score_in_range(self):
        result = compute_technicals(make_price_data())
        assert 0 <= result["composite_score"] <= 100

    def test_composite_score_is_int(self):
        result = compute_technicals(make_price_data())
        assert isinstance(result["composite_score"], int)

    def test_ema_cross_valid_values(self):
        result = compute_technicals(make_price_data())
        valid = {"golden_cross", "death_cross", "bullish", "bearish", "insufficient_data"}
        assert result["ema_cross"] in valid

    def test_bb_position_valid_values(self):
        result = compute_technicals(make_price_data())
        valid = {"upper", "mid", "lower", None}
        assert result["bb_position"] in valid

    def test_volume_ratio_positive(self):
        result = compute_technicals(make_price_data())
        assert result["volume_ratio"] > 0

    def test_bullish_trend_higher_score(self):
        bull = compute_technicals(make_bullish_data())
        flat = compute_technicals(make_flat_data())
        assert bull["composite_score"] >= flat["composite_score"], \
            f"Bull {bull['composite_score']} should >= flat {flat['composite_score']}"

    def test_bearish_trend_lower_score(self):
        bear = compute_technicals(make_bearish_data())
        flat = compute_technicals(make_flat_data())
        assert bear["composite_score"] <= flat["composite_score"], \
            f"Bear {bear['composite_score']} should <= flat {flat['composite_score']}"

    def test_insufficient_data_raises(self):
        short_data = make_price_data(n=10)
        with pytest.raises(ValueError, match="Not enough price history"):
            compute_technicals(short_data)

    def test_exactly_20_bars_ok(self):
        data = make_price_data(n=20)
        result = compute_technicals(data)
        assert "composite_score" in result

    def test_no_volume_data_defaults(self):
        data = make_price_data()
        for h in data["history"]:
            h["volume"] = 0
        result = compute_technicals(data)
        assert result["volume_ratio"] == 1.0

    def test_atr_positive(self):
        result = compute_technicals(make_price_data())
        assert result["atr"] is not None
        assert result["atr"] > 0

    def test_atr_pct_reasonable(self):
        result = compute_technicals(make_price_data())
        assert result["atr_pct"] is not None
        assert 0 < result["atr_pct"] < 20  # sanity: <20% ATR

    def test_macd_values_are_floats(self):
        result = compute_technicals(make_price_data())
        assert isinstance(result["macd"], float)
        assert isinstance(result["macd_signal"], float)
        assert isinstance(result["macd_hist"], float)

    def test_ema20_close_to_price(self):
        data = make_flat_data()
        result = compute_technicals(data)
        last_close = data["history"][-1]["close"]
        assert abs(result["ema20"] - last_close) < last_close * 0.05  # within 5%

    def test_stoch_in_range(self):
        result = compute_technicals(make_price_data())
        if result["stoch_k"] is not None:
            assert 0 <= result["stoch_k"] <= 100
            assert 0 <= result["stoch_d"] <= 100


# ── Unit tests: _tech_score() ─────────────────────────────────────────────────

class TestTechScore:

    def test_neutral_inputs_return_50(self):
        indicators = {
            "rsi": 50, "macd_hist": 0, "ema_cross": None,
            "bb_position": "mid", "volume_ratio": 1.0, "stoch_k": 50,
        }
        score = _tech_score(indicators)
        assert score == 50

    def test_all_bullish_signals_high_score(self):
        indicators = {
            "rsi": 65, "macd_hist": 0.5, "ema_cross": "golden_cross",
            "bb_position": "upper", "volume_ratio": 1.8, "stoch_k": 85,
        }
        score = _tech_score(indicators)
        assert score >= 70, f"Expected >=70, got {score}"

    def test_all_bearish_signals_low_score(self):
        indicators = {
            "rsi": 25, "macd_hist": -0.5, "ema_cross": "death_cross",
            "bb_position": "lower", "volume_ratio": 0.5, "stoch_k": 15,
        }
        score = _tech_score(indicators)
        assert score <= 30, f"Expected <=30, got {score}"

    def test_score_clamped_0_to_100(self):
        # Extreme bullish — should clamp at 100
        indicators = {
            "rsi": 75, "macd_hist": 2.0, "ema_cross": "golden_cross",
            "bb_position": "upper", "volume_ratio": 3.0, "stoch_k": 90,
        }
        assert _tech_score(indicators) <= 100

        # Extreme bearish — should clamp at 0
        indicators = {
            "rsi": 20, "macd_hist": -2.0, "ema_cross": "death_cross",
            "bb_position": "lower", "volume_ratio": 0.3, "stoch_k": 10,
        }
        assert _tech_score(indicators) >= 0

    def test_missing_keys_dont_crash(self):
        score = _tech_score({})
        assert score == 50  # all defaults = neutral

    def test_none_values_handled(self):
        indicators = {
            "rsi": None, "macd_hist": None, "ema_cross": None,
            "bb_position": None, "volume_ratio": 1.0, "stoch_k": None,
        }
        score = _tech_score(indicators)
        assert score == 50

    def test_golden_cross_adds_more_than_bullish(self):
        base = {"rsi": 50, "macd_hist": 0, "bb_position": "mid",
                "volume_ratio": 1.0, "stoch_k": 50}
        s_golden = _tech_score({**base, "ema_cross": "golden_cross"})
        s_bull   = _tech_score({**base, "ema_cross": "bullish"})
        assert s_golden > s_bull

    def test_rsi_overbought_less_bullish_than_momentum(self):
        base = {"macd_hist": 0, "ema_cross": None, "bb_position": "mid",
                "volume_ratio": 1.0, "stoch_k": 50}
        s_momentum  = _tech_score({**base, "rsi": 65})  # +10
        s_overbought = _tech_score({**base, "rsi": 75})  # +5
        assert s_momentum > s_overbought
