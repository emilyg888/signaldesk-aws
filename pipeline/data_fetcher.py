"""
Price & OHLCV data via yfinance (free, no API key needed)
Also handles FX pairs and crypto.
"""

import logging
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd

from pipeline.config import SETTINGS

log = logging.getLogger(__name__)

# Map friendly names → yfinance symbols
SYMBOL_MAP = {
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X",
}


def normalise_symbol(ticker: str) -> str:
    return SYMBOL_MAP.get(ticker.upper(), ticker.upper())


def fetch_price_data(ticker: str) -> dict:
    symbol = normalise_symbol(ticker)
    end = datetime.today()
    start = end - timedelta(days=SETTINGS["lookback_days"] + 10)  # buffer for weekends

    log.debug(f"  yfinance: {symbol} from {start.date()} to {end.date()}")
    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)

    if df.empty:
        raise ValueError(f"No price data returned for {symbol}")

    df = df.dropna()
    df.index = pd.to_datetime(df.index)

    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    close_col = "Close"
    # yfinance returns MultiIndex columns when auto_adjust=True in some versions
    if isinstance(df.columns, pd.MultiIndex):
        close_col = ("Close", symbol)

    current_price = float(latest[close_col])
    prev_price    = float(prev[close_col])
    change        = current_price - prev_price
    change_pct    = (change / prev_price) * 100

    # Build serialisable history (last 30 trading days)
    history = []
    for date, row in df.tail(SETTINGS["lookback_days"]).iterrows():
        try:
            o = float(row[("Open",  symbol)] if isinstance(df.columns, pd.MultiIndex) else row["Open"])
            h = float(row[("High",  symbol)] if isinstance(df.columns, pd.MultiIndex) else row["High"])
            l = float(row[("Low",   symbol)] if isinstance(df.columns, pd.MultiIndex) else row["Low"])
            c = float(row[("Close", symbol)] if isinstance(df.columns, pd.MultiIndex) else row["Close"])
            v = float(row[("Volume",symbol)] if isinstance(df.columns, pd.MultiIndex) else row["Volume"])
            history.append({"date": date.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c, "volume": v})
        except Exception:
            continue

    return {
        "ticker":        ticker,
        "symbol":        symbol,
        "current_price": round(current_price, 6),
        "prev_close":    round(prev_price, 6),
        "change":        round(change, 6),
        "change_pct":    round(change_pct, 3),
        "history":       history,
        "fetched_at":    datetime.now().isoformat(),
    }


def fetch_macro_data() -> dict:
    """
    Pull macro indicators:
    - VIX (fear index)          via yfinance ^VIX
    - DXY (dollar index)        via yfinance DX-Y.NYB
    - 10Y Treasury yield        via yfinance ^TNX
    - S&P 500                   via yfinance ^GSPC
    - Gold                      via yfinance GC=F
    - FRED for CPI / Fed rate   via fredapi
    """
    macro = {}

    yf_symbols = {
        "vix":   "^VIX",
        "dxy":   "DX-Y.NYB",
        "us10y": "^TNX",
        "sp500": "^GSPC",
        "gold":  "GC=F",
    }

    for key, sym in yf_symbols.items():
        try:
            df = yf.download(sym, period="5d", progress=False, auto_adjust=True)
            if not df.empty:
                col = ("Close", sym) if isinstance(df.columns, pd.MultiIndex) else "Close"
                macro[key] = round(float(df[col].iloc[-1]), 2)
        except Exception as e:
            log.warning(f"  Could not fetch {sym}: {e}")
            macro[key] = None

    # FRED data (requires fredapi + key)
    macro.update(_fetch_fred())

    # Derive composite macro score (0–100, 50 = neutral)
    score = _macro_score(macro)
    macro["composite_score"] = score

    return macro


def _fetch_fred() -> dict:
    """Fetch CPI and Fed funds rate from FRED. Returns empty dict if key not set."""
    from pipeline.config import API_KEYS
    key = API_KEYS.get("fred", "")
    if not key or key.startswith("YOUR_"):
        log.warning("  FRED API key not set — skipping CPI/Fed rate fetch")
        return {"fed_rate": 5.25, "cpi_yoy": 3.2, "gdp_qoq": 2.4}  # fallback static values

    try:
        from fredapi import Fred
        fred = Fred(api_key=key)
        fed_rate = float(fred.get_series("FEDFUNDS").iloc[-1])
        cpi      = float(fred.get_series("CPIAUCSL").pct_change(12).iloc[-1] * 100)
        gdp      = float(fred.get_series("A191RL1Q225SBEA").iloc[-1])
        return {"fed_rate": round(fed_rate, 2), "cpi_yoy": round(cpi, 2), "gdp_qoq": round(gdp, 2)}
    except Exception as e:
        log.warning(f"  FRED fetch failed: {e}")
        return {"fed_rate": None, "cpi_yoy": None, "gdp_qoq": None}


def _macro_score(macro: dict) -> int:
    """
    Heuristic macro score (0–100).
    Bearish macro = lower score, bullish = higher.
    """
    score = 50

    vix = macro.get("vix")
    if vix:
        if vix < 15:   score += 10
        elif vix < 20: score += 5
        elif vix > 30: score -= 10
        elif vix > 25: score -= 5

    us10y = macro.get("us10y")
    if us10y:
        if us10y < 3.5: score += 5
        elif us10y > 5: score -= 10
        elif us10y > 4.5: score -= 5

    fed = macro.get("fed_rate")
    if fed:
        if fed > 5: score -= 8
        elif fed < 3: score += 8

    cpi = macro.get("cpi_yoy")
    if cpi:
        if cpi < 2.5: score += 8
        elif cpi > 4:  score -= 8
        elif cpi > 3:  score -= 3

    return max(0, min(100, score))
