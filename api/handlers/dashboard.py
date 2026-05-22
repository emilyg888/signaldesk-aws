from __future__ import annotations

from datetime import datetime, timezone

from api.handlers.common import handle_errors, response, storage


@handle_errors
def handler(event, context):
    provider = storage()
    watchlist = set(provider.load_watchlist())
    summary = []
    for item in provider.get_all_latest():
        if watchlist and item.get("ticker") not in watchlist:
            continue
        price = item.get("price_data", {})
        analysis = item.get("analysis", {})
        summary.append({
            "ticker": item.get("ticker"),
            "run_date": item.get("run_date", ""),
            "price": price.get("current_price"),
            "change_pct": price.get("change_pct"),
            "agg_score": item.get("aggregate_score"),
            "bias": analysis.get("bias"),
            "conviction": analysis.get("conviction"),
            "narrative": analysis.get("narrative", ""),
        })
    return response(200, {"data": summary, "generated_at": datetime.now(timezone.utc).isoformat()})
