"""Customs -- the 관세청 수출입 무역통계 service on data.go.kr (service 1220000).

One operation, ``getItemtradeList`` (품목별 수출입실적): monthly export/import totals for
one HS code over a year-month range. The service is **XML-only** -- sending the JSON flag
makes it fault, so the session speaks XML -- and answers with a period formatted
``"2026.01"`` (dot, not a bare YYYYMM). Each item carries the HS code (``hsCode``), the
Korean item name (``statKor``), export USD/weight (``expDlr``/``expWgt``), import
USD/weight (``impDlr``/``impWgt``), and the trade balance USD (``balPayments`` =
``expDlr - impDlr``, which can be negative). The request takes ``strtYymm``/``endYymm`` =
YYYYMM range bounds and ``hsSgn`` = the HS code.
"""

from __future__ import annotations

from typing import Literal, overload

from .. import _spec
from .._spec import CleanRow, Field, Table
from ..session import DataGoKrSession
from ..types import Row

__all__ = ["AGENCY", "BASE_URL", "Customs", "SERVICE", "TABLES"]

SERVICE = "customs"
AGENCY = "관세청 (Korea Customs Service)"
BASE_URL = "https://apis.data.go.kr/1220000/Itemtrade"

ITEM_TRADE = Table(
    name="item_trade",
    endpoint="getItemtradeList",
    fields=(
        Field("year",        "period",            "date_ym", is_key=True),   # "2026.01" -> "2026-01"
        Field("hsCode",      "hs_code",           "text", is_key=True),
        Field("statKor",     "item_name",         "text"),
        Field("expDlr",      "export_usd",        "int"),
        Field("expWgt",      "export_weight_kg",  "int"),
        Field("impDlr",      "import_usd",        "int"),
        Field("impWgt",      "import_weight_kg",  "int"),
        Field("balPayments", "trade_balance_usd", "int"),
    ),
)

TABLES: dict[str, Table] = {ITEM_TRADE.name: ITEM_TRADE}


class Customs:
    """The 관세청 수출입 무역통계 surface. Construct with a data.go.kr decoding key (or
    let it resolve ``DATAGOKR_API_KEY`` / the config file)::

        customs = Customs()
        rows = customs.item_trade("8542311000", start="202601", end="202606")
    """

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0) -> None:
        self._session = DataGoKrSession(BASE_URL, api_key,
                                        timeout=timeout, response_format="xml")

    def __repr__(self) -> str:
        return f"Customs({self._session!r})"

    @overload
    def item_trade(self, hs_code: str, *, start: str, end: str,
                   clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def item_trade(self, hs_code: str, *, start: str, end: str,
                   clean: Literal[False]) -> list[Row]: ...
    @overload
    def item_trade(self, hs_code: str, *, start: str, end: str,
                   clean: bool) -> list[Row] | list[CleanRow]: ...
    def item_trade(self, hs_code: str, *, start: str, end: str,
                   clean: bool = True) -> list[Row] | list[CleanRow]:
        """품목별 수출입실적 (``getItemtradeList``) for one HS code, monthly over
        ``start``/``end`` = YYYYMM. ``clean=True`` (the default) returns typed snake_case
        rows through :data:`ITEM_TRADE`; ``clean=False`` the raw vendor rows."""
        rows = self._session.fetch(ITEM_TRADE.endpoint,
                                   strtYymm=start, endYymm=end, hsSgn=hs_code)
        return _spec.clean(rows, ITEM_TRADE) if clean else rows

    @overload
    def fetch(self, name: str, hs_code: str, *, start: str, end: str,
              clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def fetch(self, name: str, hs_code: str, *, start: str, end: str,
              clean: Literal[False]) -> list[Row]: ...
    @overload
    def fetch(self, name: str, hs_code: str, *, start: str, end: str,
              clean: bool) -> list[Row] | list[CleanRow]: ...
    def fetch(self, name: str, hs_code: str, *, start: str, end: str,
              clean: bool = True) -> list[Row] | list[CleanRow]:
        """The operation by name (``"item_trade"``; see :meth:`operations`) for one HS code
        over ``start``/``end`` = YYYYMM -- the fleet's generic entry point, mirroring the typed
        :meth:`item_trade`. Raises ``ValueError`` for an unknown ``name``;
        :class:`~pydatagokr.errors.DataGoKrError` (and subclasses) on a transport or vendor
        failure. ``clean=True`` (the default) returns typed rows; ``clean=False`` raw."""
        if name != ITEM_TRADE.name:
            raise ValueError(f"unknown operation {name!r}; valid: {list(TABLES)}")
        return self.item_trade(hs_code, start=start, end=end, clean=clean)

    @staticmethod
    def operations() -> tuple[str, ...]:
        """The operation names this surface exposes."""
        return tuple(TABLES)
