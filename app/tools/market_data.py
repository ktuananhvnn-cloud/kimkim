"""Pluggable Vietnamese market-data adapter.

IMPORTANT: VNDirect's `finfo-api` / `dchart-api` endpoints used below are the
same ones their own web app calls to draw charts - they are NOT an official,
documented, or contractually supported public API. They can change shape,
add Referer/User-Agent checks, or rate-limit without notice.

This sandbox's network egress could not reach vndirect.com.vn to verify the
exact current response shape while writing this file (DNS resolved to a
private/internal address here - typical of a locked-down dev sandbox), so
**verify these calls against the real endpoints on the VPS or your own
machine before relying on them**, and adjust `_vndirect_history_url` /
parsing below if the shape has drifted.

If VNDirect proves unreliable, switch the source with zero code changes
elsewhere in the app by setting MARKET_DATA_SOURCE=vnstock in .env - the
`vnstock` package aggregates VCI/TCBS/MSN and is actively maintained
specifically to absorb this kind of endpoint churn.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config import settings

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://dchart.vndirect.com.vn/",
}


@dataclass
class Quote:
    ticker: str
    price: float
    change_percent: float | None = None
    as_of: str | None = None


@dataclass
class Candle:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataSource(ABC):
    @abstractmethod
    def get_price(self, ticker: str) -> Quote:
        ...

    @abstractmethod
    def get_history(self, ticker: str, days: int = 30) -> list[Candle]:
        ...


class VnDirectSource(MarketDataSource):
    """Primary source, per the user's choice. Unofficial - see module docstring."""

    FINFO_URL = "https://finfo-api.vndirect.com.vn/v4/stock_prices"
    DCHART_URL = "https://dchart-api.vndirect.com.vn/dchart/history"

    def __init__(self, timeout: float = 8.0):
        self._client = httpx.Client(headers=_HEADERS, timeout=timeout)

    def get_price(self, ticker: str) -> Quote:
        ticker = ticker.upper()
        resp = self._client.get(
            self.FINFO_URL,
            params={"sort": "date", "q": f"code:{ticker}", "size": 1},
        )
        resp.raise_for_status()
        data = resp.json().get("data") or []
        if not data:
            raise LookupError(f"No price data returned for {ticker}")
        row = data[0]
        return Quote(
            ticker=ticker,
            price=float(row.get("close", row.get("basicPrice", 0))),
            change_percent=row.get("pctChange"),
            as_of=row.get("date"),
        )

    def get_history(self, ticker: str, days: int = 30) -> list[Candle]:
        ticker = ticker.upper()
        now = int(time.time())
        frm = now - days * 24 * 3600
        resp = self._client.get(
            self.DCHART_URL,
            params={"resolution": "D", "symbol": ticker, "from": frm, "to": now},
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("s") != "ok":
            return []
        return [
            Candle(
                date=time.strftime("%Y-%m-%d", time.gmtime(t)),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
            )
            for t, o, h, l, c, v in zip(
                payload["t"],
                payload["o"],
                payload["h"],
                payload["l"],
                payload["c"],
                payload["v"],
            )
        ]


class VnstockSource(MarketDataSource):
    """Fallback aggregator (VCI/TCBS/MSN) - use if VNDirect starts blocking us."""

    def __init__(self):
        from vnstock import Vnstock  # imported lazily - optional dependency

        self._vnstock = Vnstock()

    def get_price(self, ticker: str) -> Quote:
        ticker = ticker.upper()
        stock = self._vnstock.stock(symbol=ticker, source="VCI")
        df = stock.quote.history(start=_days_ago(3), end=_today(), interval="1D")
        last = df.iloc[-1]
        return Quote(ticker=ticker, price=float(last["close"]), as_of=str(last.name))

    def get_history(self, ticker: str, days: int = 30) -> list[Candle]:
        ticker = ticker.upper()
        stock = self._vnstock.stock(symbol=ticker, source="VCI")
        df = stock.quote.history(start=_days_ago(days), end=_today(), interval="1D")
        return [
            Candle(
                date=str(idx),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for idx, row in df.iterrows()
        ]


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _days_ago(days: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))


_SOURCES: dict[str, type[MarketDataSource]] = {
    "vndirect": VnDirectSource,
    "vnstock": VnstockSource,
}


@lru_cache(maxsize=1)
def get_source() -> MarketDataSource:
    source_cls = _SOURCES.get(settings.market_data_source, VnDirectSource)
    return source_cls()
