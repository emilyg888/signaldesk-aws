from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pipeline.safety.schemas import StoredRunPayload


def _clean_for_dynamodb(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _clean_for_dynamodb(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_for_dynamodb(v) for v in value]
    return value


def _restore(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {k: _restore(v) for k, v in value.items() if k not in {"PK", "SK", "entity_type"}}
    if isinstance(value, list):
        return [_restore(v) for v in value]
    return value


class DynamoDBStorageProvider:
    def __init__(self, table_name: str | None = None, region_name: str | None = None) -> None:
        self.table_name = table_name or os.getenv("SIGNALDESK_TABLE_NAME", "signaldesk-dev")
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        import boto3
        self._table = boto3.resource("dynamodb", region_name=self.region_name).Table(self.table_name)

    def init(self) -> None:
        return None

    def save_run(self, result: dict[str, Any]) -> None:
        validated = StoredRunPayload.model_validate(result).model_dump()
        ticker = validated["ticker"].upper()
        run_date = validated["run_date"]
        run_date_d = run_date[:10]
        now = datetime.now(timezone.utc).isoformat()
        full_item = {
            "PK": f"TICKER#{ticker}",
            "SK": f"RUN#{run_date_d}",
            "entity_type": "DailyRun",
            "ticker": ticker,
            "run_date": run_date,
            "run_date_d": run_date_d,
            "full_json": validated,
            "created_at": now,
        }
        latest_item = {
            "PK": "LATEST",
            "SK": f"TICKER#{ticker}",
            "entity_type": "LatestRun",
            "ticker": ticker,
            "run_date": run_date,
            "run_date_d": run_date_d,
            "full_json": validated,
            "updated_at": now,
        }
        self._table.put_item(Item=_clean_for_dynamodb(full_item))
        self._table.put_item(Item=_clean_for_dynamodb(latest_item))

    def get_latest_run(self, ticker: str) -> dict[str, Any] | None:
        resp = self._table.get_item(Key={"PK": "LATEST", "SK": f"TICKER#{ticker.upper()}"})
        item = resp.get("Item")
        return _restore(item.get("full_json")) if item else None

    def get_all_latest(self) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key
        resp = self._table.query(KeyConditionExpression=Key("PK").eq("LATEST"))
        return [_restore(item.get("full_json")) for item in resp.get("Items", [])]

    def get_history(self, ticker: str, days: int = 30) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key
        resp = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"TICKER#{ticker.upper()}") & Key("SK").begins_with("RUN#"),
            ScanIndexForward=False,
            Limit=days,
        )
        rows = []
        for item in resp.get("Items", []):
            payload = _restore(item.get("full_json", {}))
            rows.append({
                "run_date_d": payload.get("run_date", "")[:10],
                "price": payload.get("price_data", {}).get("current_price"),
                "change_pct": payload.get("price_data", {}).get("change_pct"),
                "tech_score": payload.get("technicals", {}).get("composite_score"),
                "sent_score": payload.get("sentiment", {}).get("composite_score"),
                "macro_score": payload.get("macro", {}).get("composite_score"),
                "agg_score": payload.get("aggregate_score"),
                "bias": payload.get("analysis", {}).get("bias"),
            })
        return rows

    def load_watchlist(self) -> list[str]:
        resp = self._table.get_item(Key={"PK": "CONFIG", "SK": "WATCHLIST"})
        item = resp.get("Item")
        if not item:
            return []
        return list(_restore(item).get("tickers", []))

    def save_watchlist(self, tickers: list[str]) -> None:
        cleaned = [ticker.upper().strip() for ticker in tickers if ticker.strip()]
        self._table.put_item(Item={
            "PK": "CONFIG",
            "SK": "WATCHLIST",
            "entity_type": "Watchlist",
            "tickers": cleaned,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    def create_run_status(self, run_id: str, status: str, source: str, tickers: list[str] | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._table.put_item(Item={
            "PK": "PIPELINE",
            "SK": f"RUN#{run_id}",
            "entity_type": "PipelineStatus",
            "run_id": run_id,
            "status": status,
            "source": source,
            "tickers": tickers or [],
            "created_at": now,
            "updated_at": now,
        })

    def update_run_status(self, run_id: str, status: str, **fields: Any) -> None:
        item = self.get_run_status(run_id) or {"run_id": run_id, "source": "unknown", "tickers": []}
        item.update(fields)
        item.update({"status": status, "updated_at": datetime.now(timezone.utc).isoformat()})
        self._table.put_item(Item=_clean_for_dynamodb({
            "PK": "PIPELINE",
            "SK": f"RUN#{run_id}",
            "entity_type": "PipelineStatus",
            **item,
        }))

    def get_run_status(self, run_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(Key={"PK": "PIPELINE", "SK": f"RUN#{run_id}"})
        item = resp.get("Item")
        return _restore(item) if item else None
