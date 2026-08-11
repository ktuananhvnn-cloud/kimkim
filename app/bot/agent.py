"""Claude agent: Tool Runner loop over market-data + portfolio tools.

Config editing (prompts/thresholds) is deliberately NOT exposed as a tool
here - the admin website edits those tables directly. There's no reason
for the agent to be able to rewrite its own system prompt.
"""
from __future__ import annotations

from anthropic import Anthropic, beta_tool

from app.config import settings
from app.db import supabase_client as db
from app.tools import portfolio
from app.tools.market_data import get_source

DEFAULT_SYSTEM_PROMPT = (
    "You are a personal Vietnamese stock market assistant. You only use "
    "publicly available market data and never place real trades. You may "
    "suggest ideas, but always make clear these are not financial advice "
    "and the user must place any order themselves in their own broker app. "
    "Be concise, use VND for prices, and mention when data may be delayed "
    "or outside VN market trading hours (9:00-11:30, 13:00-14:45 ICT)."
)

if settings.anthropic_api_key:
    _client = Anthropic(api_key=settings.anthropic_api_key)
else:
    # No metered API key configured - resolve credentials the same way the
    # `ant` CLI does: ANTHROPIC_AUTH_TOKEN, then the `ant auth login` OAuth
    # profile under ANTHROPIC_CONFIG_DIR. See README "Dùng gói Claude Pro/Max".
    _client = Anthropic()


@beta_tool
def get_stock_price(ticker: str) -> str:
    """Get the latest price for a Vietnamese stock ticker.

    Args:
        ticker: Stock ticker symbol, e.g. VNM, HPG, FPT.
    """
    quote = get_source().get_price(ticker)
    return f"{quote.ticker}: {quote.price:,.0f} VND (as of {quote.as_of})"


@beta_tool
def get_stock_history(ticker: str, days: int = 30) -> str:
    """Get recent daily closing prices for a ticker.

    Args:
        ticker: Stock ticker symbol.
        days: Number of calendar days of history to fetch.
    """
    candles = get_source().get_history(ticker, days=days)
    if not candles:
        return f"No history found for {ticker}."
    lines = [f"{c.date}: close {c.close:,.0f}" for c in candles[-10:]]
    return "\n".join(lines)


@beta_tool
def get_portfolio() -> str:
    """Get the user's current stock holdings with live profit/loss."""
    rows = portfolio.get_portfolio_with_pnl()
    if not rows:
        return "No holdings recorded yet."
    lines = []
    for r in rows:
        if r["pnl"] is not None:
            pnl = f"{r['pnl']:+,.0f} VND ({r['pnl_percent']:+.1f}%)"
        else:
            pnl = "n/a"
        lines.append(f"{r['ticker']}: {r['quantity']} @ {r['cost_basis']:,.0f} -> P&L {pnl}")
    return "\n".join(lines)


@beta_tool
def add_holding(ticker: str, quantity: float, cost_basis: float) -> str:
    """Record a stock holding the user owns (upserts by ticker).

    Args:
        ticker: Stock ticker symbol.
        quantity: Number of shares held.
        cost_basis: Average cost per share, in VND.
    """
    db.add_holding(ticker, quantity, cost_basis)
    return f"Recorded holding: {ticker} x{quantity} @ {cost_basis:,.0f} VND"


@beta_tool
def get_watchlist() -> str:
    """Get the user's watchlist with current prices and alert thresholds."""
    rows = portfolio.get_watchlist_with_prices()
    if not rows:
        return "Watchlist is empty."
    lines = [
        f"{r['ticker']}: {r['current_price']} "
        f"(alert high={r['alert_price_high']}, low={r['alert_price_low']})"
        for r in rows
    ]
    return "\n".join(lines)


@beta_tool
def add_watchlist_item(
    ticker: str, alert_high: float | None = None, alert_low: float | None = None
) -> str:
    """Add or update a ticker on the watchlist with optional price alert thresholds.

    Args:
        ticker: Stock ticker symbol.
        alert_high: Notify when price rises to or above this value, in VND.
        alert_low: Notify when price falls to or below this value, in VND.
    """
    db.add_watchlist_item(ticker, alert_high, alert_low)
    return f"Watching {ticker} (high={alert_high}, low={alert_low})"


_TOOLS = [
    get_stock_price,
    get_stock_history,
    get_portfolio,
    add_holding,
    get_watchlist,
    add_watchlist_item,
    {"type": "web_search_20260209", "name": "web_search"},
]


def _system_prompt() -> list[dict]:
    content = db.get_active_prompt("system") or DEFAULT_SYSTEM_PROMPT
    return [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]


def ask(chat_id: int, user_message: str) -> str:
    """Run one turn of the agent for a Telegram chat and persist history."""
    history = [
        {"role": m["role"], "content": m["content"]} for m in db.recent_messages(chat_id)
    ]
    messages = history + [{"role": "user", "content": user_message}]

    runner = _client.beta.messages.tool_runner(
        model=settings.claude_model,
        max_tokens=4096,
        system=_system_prompt(),
        tools=_TOOLS,
        messages=messages,
    )

    final = None
    for message in runner:
        final = message

    reply = next((b.text for b in final.content if b.type == "text"), "")

    db.append_message(chat_id, "user", user_message)
    db.append_message(chat_id, "assistant", reply)
    return reply
