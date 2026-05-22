"""
SQLite storage — local, free, zero setup.
Stores each daily run result as structured JSON.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from pipeline.config import PATHS

log = logging.getLogger(__name__)
DB_PATH = PATHS["db"]


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker      TEXT    NOT NULL,
                run_date    TEXT    NOT NULL,
                run_date_d  TEXT    NOT NULL,   -- date only YYYY-MM-DD
                price       REAL,
                change_pct  REAL,
                tech_score  INTEGER,
                sent_score  INTEGER,
                macro_score INTEGER,
                agg_score   INTEGER,
                bias        TEXT,
                conviction  TEXT,
                full_json   TEXT    NOT NULL,
                created_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, run_date_d)  -- one run per ticker per day
            );

            CREATE INDEX IF NOT EXISTS idx_runs_ticker_date
                ON runs(ticker, run_date_d);

            CREATE TABLE IF NOT EXISTS watchlist (
                ticker      TEXT PRIMARY KEY,
                added_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
    log.debug("DB initialised")


def save_run(result: dict):
    pd = result.get("price_data", {})
    tech = result.get("technicals", {})
    sent = result.get("sentiment", {})
    macro = result.get("macro", {})
    analysis = result.get("analysis", {})

    run_date = result.get("run_date", datetime.now().isoformat())
    run_date_d = run_date[:10]

    with get_conn() as conn:
        # Upsert: replace today's run for this ticker
        conn.execute("""
            INSERT INTO runs
              (ticker, run_date, run_date_d, price, change_pct,
               tech_score, sent_score, macro_score, agg_score,
               bias, conviction, full_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker, run_date_d) DO UPDATE SET
                run_date=excluded.run_date,
                price=excluded.price,
                change_pct=excluded.change_pct,
                tech_score=excluded.tech_score,
                sent_score=excluded.sent_score,
                macro_score=excluded.macro_score,
                agg_score=excluded.agg_score,
                bias=excluded.bias,
                conviction=excluded.conviction,
                full_json=excluded.full_json,
                created_at=CURRENT_TIMESTAMP
        """, (
            result["ticker"],
            run_date,
            run_date_d,
            pd.get("current_price"),
            pd.get("change_pct"),
            tech.get("composite_score"),
            sent.get("composite_score"),
            macro.get("composite_score"),
            result.get("aggregate_score"),
            analysis.get("bias"),
            analysis.get("conviction"),
            json.dumps(result, default=str),
        ))

        # Also upsert watchlist
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (ticker) VALUES (?)",
            (result["ticker"],),
        )

    log.debug(f"Saved run for {result['ticker']} on {run_date_d}")


def get_latest_run(ticker: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT full_json FROM runs WHERE ticker=? ORDER BY run_date DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    return json.loads(row["full_json"]) if row else None


def get_all_latest() -> list[dict]:
    """Get the most recent run for every ticker in the DB."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT full_json FROM runs
            WHERE id IN (
                SELECT MAX(id) FROM runs GROUP BY ticker
            )
            ORDER BY ticker
        """).fetchall()
    return [json.loads(r["full_json"]) for r in rows]


def get_history(ticker: str, days: int = 30) -> list[dict]:
    """Return lightweight history rows for charting."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT run_date_d, price, change_pct, tech_score,
                   sent_score, macro_score, agg_score, bias
            FROM runs
            WHERE ticker=?
            ORDER BY run_date_d DESC
            LIMIT ?
        """, (ticker, days)).fetchall()
    return [dict(r) for r in rows]


def get_watchlist_from_db() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT ticker FROM watchlist ORDER BY added_at").fetchall()
    return [r["ticker"] for r in rows]
