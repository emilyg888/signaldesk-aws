from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pipeline import storage
from pipeline.config import load_watchlist as _load_watchlist, save_watchlist as _save_watchlist


class LocalStorageProvider:
    def init(self) -> None:
        storage.init_db()

    def save_run(self, result: dict[str, Any]) -> None:
        storage.save_run(result)

    def get_latest_run(self, ticker: str) -> dict[str, Any] | None:
        return storage.get_latest_run(ticker.upper())

    def get_all_latest(self) -> list[dict[str, Any]]:
        return storage.get_all_latest()

    def get_history(self, ticker: str, days: int = 30) -> list[dict[str, Any]]:
        return storage.get_history(ticker.upper(), days)

    def load_watchlist(self) -> list[str]:
        return _load_watchlist()

    def save_watchlist(self, tickers: list[str]) -> None:
        _save_watchlist(tickers)

    def create_run_status(self, run_id: str, status: str, source: str, tickers: list[str] | None = None) -> None:
        # Local compatibility placeholder; AWS persists this in DynamoDB.
        return None

    def update_run_status(self, run_id: str, status: str, **fields: Any) -> None:
        return None

    def get_run_status(self, run_id: str) -> dict[str, Any] | None:
        return {
            "run_id": run_id,
            "status": "UNKNOWN_LOCAL",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
