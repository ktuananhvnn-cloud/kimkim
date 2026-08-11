"""Portfolio and watchlist logic - combines Supabase rows with live prices.

Kept separate from app/db/supabase_client.py (pure data access) so the P&L
math and price look-ups live in one obvious place.
"""
from __future__ import annotations

from app.db import supabase_client as db
from app.tools.market_data import get_source


def get_portfolio_with_pnl() -> list[dict]:
    holdings = db.list_holdings()
    source = get_source()
    result = []
    for h in holdings:
        try:
            price = source.get_price(h["ticker"]).price
        except Exception:
            price = None
        market_value = price * h["quantity"] if price is not None else None
        cost = h["cost_basis"] * h["quantity"]
        pnl = (market_value - cost) if market_value is not None else None
        pnl_pct = (pnl / cost * 100) if pnl is not None and cost else None
        result.append(
            {
                "ticker": h["ticker"],
                "quantity": h["quantity"],
                "cost_basis": h["cost_basis"],
                "current_price": price,
                "market_value": market_value,
                "pnl": pnl,
                "pnl_percent": pnl_pct,
            }
        )
    return result


def get_watchlist_with_prices() -> list[dict]:
    items = db.list_watchlist()
    source = get_source()
    result = []
    for item in items:
        try:
            price = source.get_price(item["ticker"]).price
        except Exception:
            price = None
        result.append(
            {
                "ticker": item["ticker"],
                "current_price": price,
                "alert_price_high": item.get("alert_price_high"),
                "alert_price_low": item.get("alert_price_low"),
            }
        )
    return result


def check_watchlist_alerts() -> list[str]:
    """Return human-readable alert messages for thresholds crossed right now.

    Dedupes against alerts_log so the same crossing doesn't re-fire all day.
    """
    messages = []
    for item in get_watchlist_with_prices():
        price = item["current_price"]
        if price is None:
            continue
        ticker = item["ticker"]
        high = item["alert_price_high"]
        low = item["alert_price_low"]
        if high is not None and price >= high and not db.was_alert_sent_today(ticker, "high"):
            msg = f"{ticker} đã vượt ngưỡng trên {high:,.0f} - giá hiện tại {price:,.0f}"
            db.log_alert(ticker, "high", msg)
            messages.append(msg)
        if low is not None and price <= low and not db.was_alert_sent_today(ticker, "low"):
            msg = f"{ticker} đã xuống dưới ngưỡng {low:,.0f} - giá hiện tại {price:,.0f}"
            db.log_alert(ticker, "low", msg)
            messages.append(msg)
    return messages
