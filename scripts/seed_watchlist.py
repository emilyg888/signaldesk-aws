from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from pipeline.providers.dynamodb_storage import DynamoDBStorageProvider

parser = argparse.ArgumentParser()
parser.add_argument("tickers", nargs="*", default=["AAPL", "NVDA", "TSLA", "BTC-USD", "EURUSD=X"])
args = parser.parse_args()
DynamoDBStorageProvider().save_watchlist(args.tickers)
print({"saved": args.tickers})
