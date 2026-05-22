"""
Unit tests — pipeline/storage.py
Tests: init_db(), save_run(), get_latest_run(), get_all_latest(),
       get_history(), get_watchlist_from_db()
Uses an in-memory SQLite DB — no file system side effects.
"""

import sys
import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_result(ticker="AAPL", score=65, bias="Bullish", date=None) -> dict:
    """Minimal valid pipeline result dict."""
    return {
        "ticker":    ticker,
        "run_date":  date or datetime.now().isoformat(),
        "price_data": {
            "current_price": 190.0,
            "change_pct":    1.2,
        },
        "technicals": {"composite_score": score},
        "sentiment":  {"composite_score": score},
        "macro":      {"composite_score": 55},
        "analysis":   {"bias": bias, "conviction": "Medium"},
        "aggregate_score": score,
        "news":   [],
        "social": [],
    }


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Redirect DB to a temp path for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("pipeline.storage.DB_PATH", db_path)
    return db_path


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestInitDb:

    def test_creates_runs_table(self, tmp_db):
        from pipeline.storage import init_db, get_conn
        init_db()
        with get_conn() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert "runs" in tables

    def test_creates_watchlist_table(self, tmp_db):
        from pipeline.storage import init_db, get_conn
        init_db()
        with get_conn() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert "watchlist" in tables

    def test_idempotent_multiple_calls(self, tmp_db):
        from pipeline.storage import init_db
        init_db()
        init_db()  # should not raise


class TestSaveRun:

    def test_saves_successfully(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_conn
        init_db()
        save_run(make_result("AAPL"))
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert count == 1

    def test_saves_correct_ticker(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_conn
        init_db()
        save_run(make_result("TSLA"))
        with get_conn() as conn:
            row = conn.execute("SELECT ticker FROM runs").fetchone()
        assert row[0] == "TSLA"

    def test_saves_correct_score(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_conn
        init_db()
        save_run(make_result("AAPL", score=72))
        with get_conn() as conn:
            row = conn.execute("SELECT agg_score FROM runs").fetchone()
        assert row[0] == 72

    def test_saves_correct_bias(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_conn
        init_db()
        save_run(make_result("AAPL", bias="Bearish"))
        with get_conn() as conn:
            row = conn.execute("SELECT bias FROM runs").fetchone()
        assert row[0] == "Bearish"

    def test_full_json_stored(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_conn
        init_db()
        result = make_result("NVDA", score=80)
        save_run(result)
        with get_conn() as conn:
            row = conn.execute("SELECT full_json FROM runs").fetchone()
        parsed = json.loads(row[0])
        assert parsed["ticker"] == "NVDA"

    def test_adds_to_watchlist(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_conn
        init_db()
        save_run(make_result("BTC-USD"))
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        assert count == 1

    def test_multiple_tickers_saved(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_conn
        init_db()
        for ticker in ["AAPL", "NVDA", "TSLA"]:
            save_run(make_result(ticker))
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert count == 3

    def test_duplicate_same_day_not_duplicated(self, tmp_db):
        """Same-day saves should update the row rather than insert a duplicate."""
        from pipeline.storage import init_db, save_run, get_conn
        init_db()
        today = datetime.now().date().isoformat() + "T00:00:00"
        save_run(make_result("AAPL", score=60, date=today))
        save_run(make_result("AAPL", score=99, date=today))
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert count == 1  # second save updates the same row

    def test_duplicate_same_day_updates_run_data(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_latest_run
        init_db()
        save_run(make_result("AAPL", score=60, date="2026-04-12T14:08:00"))
        save_run(make_result("AAPL", score=99, date="2026-04-12T15:42:00"))
        result = get_latest_run("AAPL")
        assert result["aggregate_score"] == 99
        assert result["run_date"] == "2026-04-12T15:42:00"


class TestGetLatestRun:

    def test_returns_none_when_empty(self, tmp_db):
        from pipeline.storage import init_db, get_latest_run
        init_db()
        assert get_latest_run("AAPL") is None

    def test_returns_correct_ticker(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_latest_run
        init_db()
        save_run(make_result("AAPL"))
        result = get_latest_run("AAPL")
        assert result["ticker"] == "AAPL"

    def test_returns_most_recent(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_latest_run
        init_db()
        save_run(make_result("AAPL", score=50, date="2025-01-01T09:00:00"))
        save_run(make_result("AAPL", score=80, date="2025-01-02T09:00:00"))
        result = get_latest_run("AAPL")
        assert result["aggregate_score"] == 80

    def test_wrong_ticker_returns_none(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_latest_run
        init_db()
        save_run(make_result("AAPL"))
        assert get_latest_run("TSLA") is None


class TestGetAllLatest:

    def test_returns_empty_list_when_no_data(self, tmp_db):
        from pipeline.storage import init_db, get_all_latest
        init_db()
        assert get_all_latest() == []

    def test_returns_one_per_ticker(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_all_latest
        init_db()
        for ticker in ["AAPL", "NVDA", "TSLA"]:
            save_run(make_result(ticker))
        results = get_all_latest()
        assert len(results) == 3

    def test_returns_correct_tickers(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_all_latest
        init_db()
        for ticker in ["AAPL", "BTC-USD"]:
            save_run(make_result(ticker))
        tickers = {r["ticker"] for r in get_all_latest()}
        assert tickers == {"AAPL", "BTC-USD"}


class TestGetHistory:

    def test_returns_empty_list_when_no_data(self, tmp_db):
        from pipeline.storage import init_db, get_history
        init_db()
        assert get_history("AAPL") == []

    def test_returns_history_rows(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_history
        init_db()
        save_run(make_result("AAPL", date="2025-01-01T09:00:00"))
        save_run(make_result("AAPL", date="2025-01-02T09:00:00"))
        history = get_history("AAPL")
        assert len(history) == 2

    def test_history_row_has_required_fields(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_history
        init_db()
        save_run(make_result("AAPL"))
        row = get_history("AAPL")[0]
        for field in ["run_date_d", "price", "agg_score", "bias"]:
            assert field in row

    def test_respects_days_limit(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_history
        init_db()
        for i in range(10):
            save_run(make_result("AAPL", date=f"2025-01-{i+1:02d}T09:00:00"))
        history = get_history("AAPL", days=5)
        assert len(history) == 5


class TestGetWatchlistFromDb:

    def test_returns_empty_when_no_data(self, tmp_db):
        from pipeline.storage import init_db, get_watchlist_from_db
        init_db()
        assert get_watchlist_from_db() == []

    def test_returns_saved_tickers(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_watchlist_from_db
        init_db()
        for ticker in ["AAPL", "NVDA"]:
            save_run(make_result(ticker))
        wl = get_watchlist_from_db()
        assert set(wl) == {"AAPL", "NVDA"}

    def test_no_duplicates(self, tmp_db):
        from pipeline.storage import init_db, save_run, get_watchlist_from_db
        init_db()
        save_run(make_result("AAPL", date="2025-01-01T09:00:00"))
        save_run(make_result("AAPL", date="2025-01-02T09:00:00"))
        wl = get_watchlist_from_db()
        assert wl.count("AAPL") == 1
