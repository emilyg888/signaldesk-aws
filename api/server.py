"""
SignalDesk FastAPI backend
Run with: uvicorn api.server:app --reload --port 8088
"""

import json
import math
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.storage import (
    get_latest_run, get_all_latest, get_history, init_db
)
from pipeline.config import load_watchlist, save_watchlist
from pipeline.ai_analyst import generate_earnings_story, generate_news_draft

app = FastAPI(title="SignalDesk API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve dashboard static files
DASHBOARD_DIR = ROOT / "dashboard"
if DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")


@app.on_event("startup")
def startup():
    init_db()


def clean_nan(obj):
    """Recursively replace NaN/Inf floats with None so Starlette can serialize."""
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    index_file = ROOT / "dashboard" / "index.html"
    if index_file.exists():
        return FileResponse(
            str(index_file),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return {"status": "SignalDesk API running", "docs": "/docs"}


@app.get("/api/watchlist")
def get_watchlist():
    return {"tickers": load_watchlist()}


class WatchlistUpdate(BaseModel):
    tickers: list[str]

@app.post("/api/watchlist")
def update_watchlist(body: WatchlistUpdate):
    tickers = [t.upper().strip() for t in body.tickers if t.strip()]
    save_watchlist(tickers)
    return {"tickers": tickers, "saved": True}


@app.get("/api/dashboard")
def dashboard_summary():
    """All latest runs — for the overview page."""
    watchlist = set(load_watchlist())
    results = get_all_latest()
    summary = []
    for r in results:
        if watchlist and r["ticker"] not in watchlist:
            continue
        pd = r.get("price_data", {})
        analysis = r.get("analysis", {})
        summary.append({
            "ticker":      r["ticker"],
            "run_date":    r.get("run_date", ""),
            "price":       pd.get("current_price"),
            "change_pct":  pd.get("change_pct"),
            "agg_score":   r.get("aggregate_score"),
            "bias":        analysis.get("bias"),
            "conviction":  analysis.get("conviction"),
            "narrative":   analysis.get("narrative", ""),
        })
    return clean_nan({"data": summary, "generated_at": datetime.now().isoformat()})


@app.get("/api/ticker/{ticker}")
def ticker_detail(ticker: str):
    """Full detail for a single ticker."""
    result = get_latest_run(ticker.upper())
    if not result:
        raise HTTPException(404, f"No data found for {ticker}. Run the pipeline first.")
    return clean_nan(result)


@app.post("/api/ticker/{ticker}/earnings-story")
def ticker_earnings_story(ticker: str):
    """Generate a first-pass corporate earnings story for one ticker."""
    symbol = ticker.upper()
    result = get_latest_run(symbol)
    if not result:
        raise HTTPException(404, f"No data found for {ticker}. Run the pipeline first.")
    return clean_nan({
        "ticker": symbol,
        "generated_at": datetime.now().isoformat(),
        "content": generate_earnings_story(symbol, result),
    })


@app.post("/api/ticker/{ticker}/news-draft")
def ticker_news_draft(ticker: str):
    """Generate first-pass news content from stored ticker data."""
    symbol = ticker.upper()
    result = get_latest_run(symbol)
    if not result:
        raise HTTPException(404, f"No data found for {ticker}. Run the pipeline first.")
    return clean_nan({
        "ticker": symbol,
        "generated_at": datetime.now().isoformat(),
        "content": generate_news_draft(symbol, result),
    })


@app.get("/api/ticker/{ticker}/history")
def ticker_history(ticker: str, days: int = 30):
    history = get_history(ticker.upper(), days)
    return clean_nan({"ticker": ticker.upper(), "history": history})


@app.post("/api/run")
def trigger_run(tickers: list[str] | None = None):
    """Trigger the pipeline manually (runs in background subprocess)."""
    script = ROOT / "pipeline" / "run_pipeline.py"
    try:
        subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"status": "started", "message": "Pipeline running in background. Refresh in ~2 minutes."}
    except Exception as e:
        raise HTTPException(500, f"Failed to start pipeline: {e}")


@app.get("/api/status")
def status():
    results = get_all_latest()
    last_run = max((r.get("run_date", "") for r in results), default=None)
    return {
        "status":     "ok",
        "tickers":    len(results),
        "last_run":   last_run,
        "server_time": datetime.now().isoformat(),
    }
