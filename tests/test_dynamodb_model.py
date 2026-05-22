from __future__ import annotations

from pipeline.providers.dynamodb_storage import _restore


def test_latest_key_shape_documented():
    assert {"PK": "LATEST", "SK": "TICKER#AAPL"}["PK"] == "LATEST"


def test_restore_removes_internal_keys():
    assert _restore({"PK": "LATEST", "SK": "TICKER#AAPL", "entity_type": "LatestRun", "ticker": "AAPL"}) == {"ticker": "AAPL"}
