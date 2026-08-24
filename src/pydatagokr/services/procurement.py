"""Procurement -- 조달청 나라장터 입찰공고정보 on data.go.kr (service 1230000).

나라장터 bid announcements, one operation per 업무구분: `goods` (물품), `services` (용역),
`construction` (공사), `foreign` (외자). The vendor requires the operation to match the
announcement's 업무구분 -- a 공사 announcement answers only on the 공사 operation -- so each
is its own method here. A row is one 입찰공고, keyed by its number and ordinal
(``notice_no`` + ``notice_ord``); the 추정가격·배정예산 are exact won integers, the
announcement/close/opening times are the vendor's ``YYYY-MM-DD HH:MM:SS`` text.

A query is a time window over the 공고 게시일시 (``begin``/``end`` = YYYYMMDDHHMM) plus the
``query_basis`` basis (``"1"`` 공고게시일시, ``"2"`` 개찰일시). Only a curated header subset of
the vendor's ~100 fields is mapped -- number, name, agencies, method, the money, the times,
and the detail URL. ``clean=True`` (the default) returns typed rows, ``clean=False`` the raw
vendor rows. The service answers XML.
"""

from __future__ import annotations

from typing import Literal, overload

from .. import _spec
from .._spec import CleanRow, Field, Table
from ..session import DataGoKrSession
from ..types import Row

__all__ = ["AGENCY", "BASE_URL", "Procurement", "QueryBasis", "SERVICE", "TABLES"]

SERVICE = "procurement"
AGENCY = "조달청 (Public Procurement Service, 나라장터)"
BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"

# The window basis the vendor accepts as ``inqryDiv`` -- a closed two-value set.
QueryBasis = Literal["1", "2"]   # "1" 공고게시일시, "2" 개찰일시

# The header fields shared by every 업무구분's 입찰공고목록. 배정예산 is absent on 공사
# announcements, so ``budget_amount`` stays ``None`` there rather than being a separate table.
_BID = (
    Field("bidNtceNo",         "notice_no",        "text", is_key=True),   # 입찰공고번호
    Field("bidNtceOrd",        "notice_ord",       "text", is_key=True),   # 입찰공고차수
    Field("bidNtceNm",         "notice_name",      "text"),                # 입찰공고명
    Field("ntceKindNm",        "notice_kind",      "text"),                # 공고종류(재공고 등)
    Field("ntceInsttNm",       "notice_agency",    "text"),                # 공고기관
    Field("dminsttNm",         "demand_agency",    "text"),                # 수요기관
    Field("bidMethdNm",        "bid_method",       "text"),                # 입찰방식(전자입찰 등)
    Field("cntrctCnclsMthdNm", "contract_method",  "text"),                # 계약체결방법
    Field("bidNtceDt",         "notice_at",        "text"),                # 입찰공고일시
    Field("bidClseDt",         "bid_close_at",     "text"),                # 입찰마감일시
    Field("opengDt",           "opening_at",       "text"),                # 개찰일시
    Field("presmptPrce",       "estimated_price",  "int"),                 # 추정가격(원)
    Field("asignBdgtAmt",      "budget_amount",    "int"),                 # 배정예산(원)
    Field("ntceInsttOfclNm",   "officer_name",     "text"),                # 공고담당자
    Field("bidNtceDtlUrl",     "notice_url",       "text"),                # 공고상세 URL
    Field("rgstDt",            "registered_at",    "text"),                # 등록일시
)

GOODS = Table("goods", "getBidPblancListInfoThngPPSSrch",
              _BID, is_wide_key=True)
SERVICES = Table("services", "getBidPblancListInfoServcPPSSrch",
                 _BID, is_wide_key=True)
CONSTRUCTION = Table("construction", "getBidPblancListInfoCnstwkPPSSrch",
                     _BID, is_wide_key=True)
FOREIGN = Table("foreign", "getBidPblancListInfoFrgcptPPSSrch",
                _BID, is_wide_key=True)

TABLES: dict[str, Table] = {table.name: table for table in (
    GOODS, SERVICES, CONSTRUCTION, FOREIGN,
)}


class Procurement:
    """The 나라장터 입찰공고 surface. Construct with a data.go.kr decoding key (or let it
    resolve ``DATAGOKR_API_KEY`` / the config file)::

        procurement = Procurement()
        rows = procurement.services(begin="202608010000", end="202608102359")   # 용역 입찰공고
        rows = procurement.construction(begin="202608010000", end="202608102359")
    """

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0) -> None:
        self._session = DataGoKrSession(BASE_URL, api_key,
                                        timeout=timeout, response_format="xml")

    def __repr__(self) -> str:
        return f"Procurement({self._session!r})"

    @overload
    def goods(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
              clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def goods(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
              clean: Literal[False]) -> list[Row]: ...
    @overload
    def goods(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
              clean: bool) -> list[Row] | list[CleanRow]: ...
    def goods(self, *, begin: str, end: str, query_basis: QueryBasis = "1",
              clean: bool = True) -> list[Row] | list[CleanRow]:
        """물품 입찰공고 over the ``begin``..``end`` window (YYYYMMDDHHMM). ``query_basis`` is
        the window basis (``"1"`` 공고게시일시, ``"2"`` 개찰일시). ``clean=True`` (the default)
        returns typed rows; ``clean=False`` raw."""
        return self.fetch("goods", begin=begin, end=end, query_basis=query_basis, clean=clean)

    @overload
    def services(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
                 clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def services(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
                 clean: Literal[False]) -> list[Row]: ...
    @overload
    def services(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
                 clean: bool) -> list[Row] | list[CleanRow]: ...
    def services(self, *, begin: str, end: str, query_basis: QueryBasis = "1",
                 clean: bool = True) -> list[Row] | list[CleanRow]:
        """용역 입찰공고. Args as :meth:`goods`."""
        return self.fetch("services", begin=begin, end=end, query_basis=query_basis, clean=clean)

    @overload
    def construction(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
                     clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def construction(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
                     clean: Literal[False]) -> list[Row]: ...
    @overload
    def construction(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
                     clean: bool) -> list[Row] | list[CleanRow]: ...
    def construction(self, *, begin: str, end: str, query_basis: QueryBasis = "1",
                     clean: bool = True) -> list[Row] | list[CleanRow]:
        """공사 입찰공고 (배정예산 미제공 -- ``budget_amount`` is ``None``). Args as
        :meth:`goods`."""
        return self.fetch("construction", begin=begin, end=end,
                          query_basis=query_basis, clean=clean)

    @overload
    def foreign(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
                clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def foreign(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
                clean: Literal[False]) -> list[Row]: ...
    @overload
    def foreign(self, *, begin: str, end: str, query_basis: QueryBasis = ...,
                clean: bool) -> list[Row] | list[CleanRow]: ...
    def foreign(self, *, begin: str, end: str, query_basis: QueryBasis = "1",
                clean: bool = True) -> list[Row] | list[CleanRow]:
        """외자 입찰공고. Args as :meth:`goods`."""
        return self.fetch("foreign", begin=begin, end=end, query_basis=query_basis, clean=clean)

    @overload
    def fetch(self, name: str, *, begin: str, end: str, query_basis: QueryBasis = ...,
              clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def fetch(self, name: str, *, begin: str, end: str, query_basis: QueryBasis = ...,
              clean: Literal[False]) -> list[Row]: ...
    @overload
    def fetch(self, name: str, *, begin: str, end: str, query_basis: QueryBasis = ...,
              clean: bool) -> list[Row] | list[CleanRow]: ...
    def fetch(self, name: str, *, begin: str, end: str, query_basis: QueryBasis = "1",
              clean: bool = True) -> list[Row] | list[CleanRow]:
        """Any of the four 업무구분 by name (see :meth:`operations`) over one time window.
        Raises ``ValueError`` for an unknown ``name``;
        :class:`~pydatagokr.errors.DataGoKrError` (and subclasses) on a transport or vendor
        failure. ``clean=True`` (the default) returns typed rows; ``clean=False`` raw."""
        try:
            table = TABLES[name]
        except KeyError:
            raise ValueError(f"unknown operation {name!r}; valid: {list(TABLES)}") from None
        rows = self._session.fetch(table.endpoint, type="xml", inqryDiv=query_basis,
                                   inqryBgnDt=begin, inqryEndDt=end)
        return _spec.clean(rows, table) if clean else rows

    @staticmethod
    def operations() -> tuple[str, ...]:
        """The operation names :meth:`fetch` accepts."""
        return tuple(TABLES)
