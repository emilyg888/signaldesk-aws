"""
Technical indicator computation using pandas.
Covers RSI, MACD, EMA, Bollinger Bands, ATR, Volume ratio.
"""

import logging
import pandas as pd

log = logging.getLogger(__name__)


def _latest_float(series: pd.Series | None, digits: int) -> float | None:
    if series is None or series.empty:
        return None
    value = series.iloc[-1]
    if pd.isna(value):
        return None
    return round(float(value), digits)


def compute_technicals(price_data: dict) -> dict:
    history = price_data["history"]
    if len(history) < 20:
        raise ValueError("Not enough price history for technical analysis (need 20+ bars)")

    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df.columns = [c.lower() for c in df.columns]

    results = {}

    # ── RSI ──────────────────────────────────────────────────────────────────
    rsi = _rsi(df["close"], length=14)
    results["rsi"] = _latest_float(rsi, 2)

    # ── MACD ─────────────────────────────────────────────────────────────────
    macd_df = _macd(df["close"], fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        results["macd"] = _latest_float(macd_df["MACD_12_26_9"], 4)
        results["macd_signal"] = _latest_float(macd_df["MACDs_12_26_9"], 4)
        results["macd_hist"] = _latest_float(macd_df["MACDh_12_26_9"], 4)
    else:
        results["macd"] = results["macd_signal"] = results["macd_hist"] = None

    # ── EMA 20 / 50 ──────────────────────────────────────────────────────────
    ema20 = _ema(df["close"], length=20)
    ema50 = _ema(df["close"], length=50) if len(df) >= 50 else None

    results["ema20"] = _latest_float(ema20, 4)
    results["ema50"] = _latest_float(ema50, 4)

    if results["ema20"] and results["ema50"]:
        prev_ema20 = None if pd.isna(ema20.iloc[-2]) else float(ema20.iloc[-2])
        prev_ema50 = None if pd.isna(ema50.iloc[-2]) else float(ema50.iloc[-2])
        if prev_ema20 is None or prev_ema50 is None:
            results["ema_cross"] = "insufficient_data"
        elif prev_ema20 <= prev_ema50 and results["ema20"] > results["ema50"]:
            results["ema_cross"] = "golden_cross"
        elif prev_ema20 >= prev_ema50 and results["ema20"] < results["ema50"]:
            results["ema_cross"] = "death_cross"
        elif results["ema20"] > results["ema50"]:
            results["ema_cross"] = "bullish"
        else:
            results["ema_cross"] = "bearish"
    else:
        results["ema_cross"] = "insufficient_data"

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb = _bbands(df["close"], length=20, std=2)
    if bb is not None and not bb.empty:
        close = float(df["close"].iloc[-1])
        results["bb_upper"] = _latest_float(bb["BBU_20_2.0_2.0"], 4)
        results["bb_mid"] = _latest_float(bb["BBM_20_2.0_2.0"], 4)
        results["bb_lower"] = _latest_float(bb["BBL_20_2.0_2.0"], 4)
        if results["bb_upper"] is not None and results["bb_mid"] not in (None, 0) and results["bb_lower"] is not None:
            results["bb_width"] = round((results["bb_upper"] - results["bb_lower"]) / results["bb_mid"], 4)
        else:
            results["bb_width"] = None

        if results["bb_upper"] is not None and close >= results["bb_upper"] * 0.99:
            results["bb_position"] = "upper"
        elif results["bb_lower"] is not None and close <= results["bb_lower"] * 1.01:
            results["bb_position"] = "lower"
        else:
            results["bb_position"] = "mid"
    else:
        results["bb_position"] = None

    # ── ATR (volatility) ─────────────────────────────────────────────────────
    atr = _atr(df["high"], df["low"], df["close"], length=14)
    results["atr"] = _latest_float(atr, 4)
    results["atr_pct"] = round(results["atr"] / float(df["close"].iloc[-1]) * 100, 2) if results["atr"] else None

    # ── Volume ratio ─────────────────────────────────────────────────────────
    if "volume" in df.columns and df["volume"].sum() > 0:
        avg_vol = df["volume"].tail(20).mean()
        cur_vol = df["volume"].iloc[-1]
        results["volume_ratio"] = round(cur_vol / avg_vol, 2) if avg_vol > 0 else 1.0
    else:
        results["volume_ratio"] = 1.0

    # ── Stochastic ───────────────────────────────────────────────────────────
    stoch = _stoch(df["high"], df["low"], df["close"])
    if stoch is not None and not stoch.empty:
        results["stoch_k"] = _latest_float(stoch["STOCHk_14_3_3"], 2)
        results["stoch_d"] = _latest_float(stoch["STOCHd_14_3_3"], 2)
    else:
        results["stoch_k"] = results["stoch_d"] = None

    # ── Composite technical score (0–100) ────────────────────────────────────
    results["composite_score"] = _tech_score(results)

    return results


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50)
    return rsi


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd = _ema(close, fast) - _ema(close, slow)
    signal_line = macd.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd - signal_line
    return pd.DataFrame({
        "MACD_12_26_9": macd,
        "MACDs_12_26_9": signal_line,
        "MACDh_12_26_9": hist,
    })


def _bbands(close: pd.Series, length: int = 20, std: float = 2) -> pd.DataFrame:
    mid = close.rolling(window=length, min_periods=length).mean()
    deviation = close.rolling(window=length, min_periods=length).std()
    upper = mid + deviation * std
    lower = mid - deviation * std
    return pd.DataFrame({
        "BBL_20_2.0_2.0": lower,
        "BBM_20_2.0_2.0": mid,
        "BBU_20_2.0_2.0": upper,
    })


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    true_range = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def _stoch(high: pd.Series, low: pd.Series, close: pd.Series, k_length: int = 14, k_smooth: int = 3, d_smooth: int = 3) -> pd.DataFrame:
    lowest_low = low.rolling(window=k_length, min_periods=k_length).min()
    highest_high = high.rolling(window=k_length, min_periods=k_length).max()
    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, pd.NA)
    stoch_k = raw_k.rolling(window=k_smooth, min_periods=k_smooth).mean()
    stoch_d = stoch_k.rolling(window=d_smooth, min_periods=d_smooth).mean()
    return pd.DataFrame({
        "STOCHk_14_3_3": stoch_k,
        "STOCHd_14_3_3": stoch_d,
    })


def _tech_score(t: dict) -> int:
    score = 50

    # RSI
    rsi = t.get("rsi")
    if rsi:
        if 40 <= rsi <= 60:   score += 0    # neutral
        elif 60 < rsi <= 70:  score += 10   # bullish momentum
        elif rsi > 70:        score += 5    # overbought — slightly less bullish
        elif 30 <= rsi < 40:  score -= 5    # approaching oversold
        elif rsi < 30:        score -= 10   # oversold

    # MACD
    macd_hist = t.get("macd_hist")
    if macd_hist is not None:
        if macd_hist > 0:    score += 10
        elif macd_hist < 0:  score -= 10

    # EMA cross
    cross = t.get("ema_cross")
    if cross == "golden_cross":  score += 15
    elif cross == "bullish":     score += 8
    elif cross == "death_cross": score -= 15
    elif cross == "bearish":     score -= 8

    # Bollinger
    bb_pos = t.get("bb_position")
    if bb_pos == "upper":  score += 5
    elif bb_pos == "lower": score -= 8

    # Volume
    vol = t.get("volume_ratio", 1.0)
    if vol > 1.5:   score += 8
    elif vol > 1.2: score += 3
    elif vol < 0.7: score -= 5

    # Stochastic
    k = t.get("stoch_k")
    if k:
        if k > 80:  score += 3
        elif k < 20: score -= 8

    return max(0, min(100, score))
