from __future__ import annotations

import argparse

from pipeline.providers.dynamodb_storage import DynamoDBStorageProvider

parser = argparse.ArgumentParser()
parser.add_argument("tickers", nargs="*", default=["AAPL", "NVDA", "TSLA", "BTC-USD", "EURUSD=X"])
args = parser.parse_args()
DynamoDBStorageProvider().save_watchlist(args.tickers)
print({"saved": args.tickers})
