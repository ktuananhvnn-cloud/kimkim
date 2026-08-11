"""Thin wrapper around the Supabase client plus small data-access helpers.

Kept deliberately un-abstracted (no repository/ORM layer) - this is a
single-owner app with ~7 tables, plain query calls are easier to read and
change than a framework would be.
"""
from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)


# ---------- holdings ----------

def list_holdings() -> list[dict]:
    resp = get_client().table("holdings").select("*").order("ticker").execute()
    return resp.data


def add_holding(ticker: str, quantity: float, cost_basis: float, note: str = "") -> dict:
    resp = (
        get_client()
        .table("holdings")
        .insert(
            {
                "ticker": ticker.upper(),
                "quantity": quantity,
                "cost_basis": cost_basis,
                "notes": note,
            }
        )
        .execute()
    )
    return resp.data[0]


def remove_holding(ticker: str) -> None:
    get_client().table("holdings").delete().eq("ticker", ticker.upper()).execute()


# ---------- watchlist ----------

def list_watchlist() -> list[dict]:
    resp = get_client().table("watchlist").select("*").order("ticker").execute()
    return resp.data


def add_watchlist_item(
    ticker: str, alert_high: float | None = None, alert_low: float | None = None
) -> dict:
    resp = (
        get_client()
        .table("watchlist")
        .upsert(
            {
                "ticker": ticker.upper(),
                "alert_price_high": alert_high,
                "alert_price_low": alert_low,
            },
            on_conflict="ticker",
        )
        .execute()
    )
    return resp.data[0]


def remove_watchlist_item(ticker: str) -> None:
    get_client().table("watchlist").delete().eq("ticker", ticker.upper()).execute()


# ---------- conversation history ----------

def append_message(chat_id: int, role: str, content: dict | list | str) -> None:
    get_client().table("conversation_messages").insert(
        {"telegram_chat_id": chat_id, "role": role, "content": content}
    ).execute()


def recent_messages(chat_id: int, limit: int = 40) -> list[dict]:
    resp = (
        get_client()
        .table("conversation_messages")
        .select("role,content,created_at")
        .eq("telegram_chat_id", chat_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(resp.data))


# ---------- prompts (versioned) ----------

def get_active_prompt(name: str = "system") -> str | None:
    resp = (
        get_client()
        .table("prompts")
        .select("content")
        .eq("name", name)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return resp.data[0]["content"] if resp.data else None


def save_prompt_version(name: str, content: str) -> dict:
    """Deactivate the current active version and insert a new active one."""
    client = get_client()
    client.table("prompts").update({"is_active": False}).eq("name", name).eq(
        "is_active", True
    ).execute()
    current = (
        client.table("prompts")
        .select("version")
        .eq("name", name)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    next_version = (current.data[0]["version"] + 1) if current.data else 1
    resp = (
        client.table("prompts")
        .insert(
            {
                "name": name,
                "content": content,
                "version": next_version,
                "is_active": True,
            }
        )
        .execute()
    )
    return resp.data[0]


def list_prompt_versions(name: str = "system") -> list[dict]:
    resp = (
        get_client()
        .table("prompts")
        .select("version,is_active,updated_at")
        .eq("name", name)
        .order("version", desc=True)
        .execute()
    )
    return resp.data


# ---------- config (non-secret key/value) ----------

def get_config(key: str, default=None):
    resp = get_client().table("config").select("value").eq("key", key).limit(1).execute()
    return resp.data[0]["value"] if resp.data else default


def set_config(key: str, value) -> None:
    get_client().table("config").upsert({"key": key, "value": value}).execute()


# ---------- price cache ----------

def get_cached_price(ticker: str, max_age_seconds: int = 30) -> float | None:
    resp = (
        get_client()
        .table("price_cache")
        .select("price,fetched_at")
        .eq("ticker", ticker.upper())
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    from datetime import datetime, timezone

    fetched_at = datetime.fromisoformat(resp.data[0]["fetched_at"])
    age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
    return resp.data[0]["price"] if age <= max_age_seconds else None


def set_cached_price(ticker: str, price: float) -> None:
    get_client().table("price_cache").upsert(
        {"ticker": ticker.upper(), "price": price}
    ).execute()


# ---------- alerts log (dedupe) ----------

def was_alert_sent_today(ticker: str, alert_type: str) -> bool:
    resp = (
        get_client()
        .table("alerts_log")
        .select("id")
        .eq("ticker", ticker.upper())
        .eq("alert_type", alert_type)
        .gte("triggered_at", _today_start_iso())
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def log_alert(ticker: str, alert_type: str, message: str) -> None:
    get_client().table("alerts_log").insert(
        {"ticker": ticker.upper(), "alert_type": alert_type, "message": message}
    ).execute()


def _today_start_iso() -> str:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
