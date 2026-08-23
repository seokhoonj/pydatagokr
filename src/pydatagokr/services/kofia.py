"""KOFIA -- the 금융투자협회 (KOFIA) 종합통계 service on data.go.kr (service 1160100).

One service with eight operations. The two most-watched flow series -- 증시자금추이
(예탁금·미수금·반대매매, ``market_funds``) and 신용공여잔고추이 (신용거래융자·대주·담보융자,
``credit_balance``) -- are typed methods, and every operation is reachable through
:meth:`KOFIA.fetch` by name. Each operation's :class:`~pydatagokr._spec.Table` maps the
vendor's field tokens (``invrDpsgAmt``, ``crdTrFingWhl``, ...) to clean snake_case
columns; ``clean=True`` (the default) returns those typed rows, ``clean=False`` the raw
vendor rows.

Dates are the service's own format: 일별 오퍼레이션은 ``begin``/``end`` = YYYYMMDD, 월별
오퍼레이션(신탁규모·DLS/DLB 등)은 YYYYMM (a YYYYMMDD bound is truncated to its YYYYMM
prefix). Data updates once a day and starts 2021-11-16.
"""

from __future__ import annotations

from typing import Literal, overload

from .. import _spec
from .._spec import CleanRow, Field, Table
from ..session import DataGoKrSession
from ..types import Row

__all__ = ["AGENCY", "BASE_URL", "KOFIA", "SERVICE", "TABLES"]

SERVICE = "kofia"
AGENCY = "금융투자협회 (Korea Financial Investment Association)"
BASE_URL = "https://apis.data.go.kr/1160100/service/GetKofiaStatisticsInfoService"

# The operation paths come from the service's Call Back URLs; the 증시자금 op path is
# lowercase 'get' despite the capitalised entry in the 상세기능 목록 -- the URL is the
# authority, live-verified.

# -- daily flow series (date is the whole key) -------------------------------------------

MARKET_FUNDS = Table("market_funds", "getSecuritiesMarketTotalCapitalInfo", (
    Field("basDt",                     "base_date",                       "date_ymd", is_key=True),
    Field("invrDpsgAmt",               "investor_deposit",                "int"),                     # 투자자예탁금
    Field("onbdDrvPrdTrRcAdvAmt",      "derivatives_deposit",             "int"),                     # 장내파생상품거래예수금
    Field("toCstRpchCndBndSlgBal",     "customer_rp_sale_balance",        "int"),                     # 대고객RP매도잔고
    Field("brkTrdUcolMny",             "brokerage_receivable",            "int"),                     # 위탁매매미수금
    Field("brkTrdUcolMnyVsOppsTrdAmt", "forced_sell_amount",              "int"),                     # 미수금대비반대매매금액
    Field("ucolMnyVsOppsTrdRlImpt",    "forced_sell_to_receivable_ratio", "ratio"),                   # 미수금대비반대매매비중(%)
))

CREDIT_BALANCE = Table("credit_balance", "getGrantingOfCreditBalanceInfo", (
    Field("basDt",           "base_date",          "date_ymd", is_key=True),
    Field("crdTrFingWhl",    "margin_loan_total",  "int"),                     # 신용거래융자 전체
    Field("crdTrFingScrs",   "margin_loan_kospi",  "int"),                     # 신용거래융자 유가증권
    Field("crdTrFingKosdaq", "margin_loan_kosdaq", "int"),                     # 신용거래융자 코스닥
    Field("crdTrLndrWhl",    "stock_loan_total",   "int"),                     # 신용거래대주 전체 (broker lends shares)
    Field("crdTrLndrScrs",   "stock_loan_kospi",   "int"),                     # 신용거래대주 유가증권
    Field("crdTrLndrKosdaq", "stock_loan_kosdaq",  "int"),                     # 신용거래대주 코스닥
    Field("sbscCapLn",       "subscription_loan",  "int"),                     # 청약자금 대출
    Field("dpsgScrtMogFing", "collateral_loan",    "int"),                     # 예탁증권 담보융자
))

# -- category-dimensioned series (date + dimensions are the key) -------------------------

FUND_NET_ASSET = Table("fund_net_asset", "getFundTotalNetEssetInfo", (
    Field("basDt",      "base_date",       "date_ymd", is_key=True),
    Field("ctg",        "fund_type",       "text", is_key=True),       # 펀드 구분 (PEF ...)
    Field("tstMthdCtg", "offering_type",   "text", is_key=True),       # 공모/사모
    Field("nPptTotAmt", "net_asset_total", "int"),                     # 순자산총액
))

CMA_STATUS = Table("cma_status", "getCMAStatus", (
    Field("basDt",       "base_date",             "date_ymd", is_key=True),
    Field("mngInvTgt",   "management_target",     "text", is_key=True),       # RP형/MMF형/합계 ...
    Field("invrCtg",     "investor_type",         "text", is_key=True),       # 개인/기관
    Field("scrtCmpyCnt", "securities_firm_count", "int"),                     # 증권회사수
    Field("actCnt",      "account_count",         "int"),                     # 계좌수
    Field("actBal",      "account_balance",       "int"),                     # 계좌잔액
))

DLS_DLB = Table("dls_dlb", "getDLSAndDLBInfo", (
    Field("basDt",        "base_ym",       "date_ym", is_key=True),
    Field("ctgDlbDls",    "product_type",  "text", is_key=True),      # 원금보장/비보장/합계
    Field("ctgPrplcPsub", "offering_type", "text", is_key=True),      # 공모/사모/합계
    Field("presCtg",      "status_type",   "text", is_key=True),      # 발행실적/미상환잔고/상환현황
    Field("amt",          "amount_krw",    "int"),                    # 금액 (원)
    Field("ccnt",         "deal_count",    "int"),                    # 건수
))

ELS_ELB = Table("els_elb", "getELSAndELBInfo", (
    Field("basDt",        "base_ym",       "date_ym", is_key=True),
    Field("ctgElbEls",    "product_type",  "text", is_key=True),      # ELB/ELS 구분
    Field("ctgPrplcPsub", "offering_type", "text", is_key=True),      # 공모/사모
    Field("presCtg",      "status_type",   "text", is_key=True),      # 발행실적/미상환잔고/상환현황
    Field("amt",          "amount_krw",    "int"),                    # 금액 (원)
    Field("ccnt",         "deal_count",    "int"),                    # 건수
))

TRUST_SCALE = Table("trust_scale", "getTrustScaleInfo", (
    Field("basYm",  "base_ym",       "date_ym", is_key=True),
    Field("bzds",   "sector",        "text", is_key=True),      # 업권 (증권 ...)
    Field("tstCtg", "trust_type",    "text", is_key=True),      # 신탁구분
    Field("kind",   "trust_kind",    "text", is_key=True),      # 종류
    Field("iqBs",   "measure_basis", "text", is_key=True),      # 조회기준 (고객수/계약수/수탁총액)
    Field("val",    "measure_value", "int"),                    # 조회기준별 값
))

# high-dimensional product-level series -> surrogate id + per-month replace (a 10-column,
# 200-char-name composite key would blow a btree index-row limit).
OVERSEAS_DERIVATIVES = Table("overseas_derivatives", "getDerivationProductTradingInfo", (
    Field("basDt",           "base_ym",                "date_ym", is_key=True),
    Field("byPrdGrp",        "product_group",          "text", is_key=True),      # 상품군별
    Field("actCtg",          "account_type",           "text", is_key=True),      # 자기/중개/총괄
    Field("ctgBsonCntrForm", "contract_form",          "text", is_key=True),      # 계약형태 (콜옵션 ...)
    Field("prdNm",           "product_name",           "text", is_key=True),      # 상품명 (거래소 등록명)
    Field("brkPn",           "customer_type",          "text", is_key=True),      # 위탁자 (개인/법인 ...)
    Field("xchNm",           "exchange",               "text", is_key=True),      # 거래소명
    Field("csfBsonCntrForm", "contract_class",         "text", is_key=True),      # 계약형태 분류
    Field("byNtnl",          "country",                "text", is_key=True),      # 국가별
    Field("prdGrp",          "underlying_asset_group", "text", is_key=True),      # 기초자산 분류
    Field("trqu",            "trade_volume",           "int"),                    # 거래량
    Field("trPrcUsd",        "trade_value_usd",        "int"),                    # 거래대금(USD)
), is_wide_key=True)


TABLES: dict[str, Table] = {table.name: table for table in (
    MARKET_FUNDS, CREDIT_BALANCE, TRUST_SCALE, FUND_NET_ASSET,
    CMA_STATUS, DLS_DLB, ELS_ELB, OVERSEAS_DERIVATIVES,
)}


def _date_filters(table: Table, begin: str | None, end: str | None) -> dict[str, str | None]:
    """The vendor's begin/end query params for fetching ``table``, derived from its date
    field: the field's own vendor token gives the param base -- ``beginBasDt``/``endBasDt``
    (daily) or ``beginBasYm``/``endBasYm``. A ``None`` bound stays ``None`` (the session omits
    it). Kept beside the KOFIA tables so a consumer never re-derives the vendor names.

    The vendor compares the bounds against a fixed-width ``basDt`` STRING (YYYYMMDD daily,
    YYYYMM monthly) as a half-open range -- ``begin <= basDt < end`` -- verified live for
    every operation. So each bound is normalised to the field's width, and the end is pushed
    up one sort step (a trailing ``9``) to make the caller's ``end`` inclusive; otherwise the
    last day/month, and a ``begin == end`` single-point query, are silently dropped."""
    date_field = next(
        (field for field in table.fields if field.kind.startswith("date")), None)
    if date_field is None:
        return {}   # a table with no date field takes no begin/end bounds
    width = 6 if date_field.kind == "date_ym" else 8
    lo = begin[:width] if begin else None
    hi = end[:width] + "9" if end else None
    cap = date_field.token[0].upper() + date_field.token[1:]
    return {f"begin{cap}": lo, f"end{cap}": hi}


class KOFIA:
    """The KOFIA 종합통계 surface. Construct with a data.go.kr decoding key (or let it
    resolve ``DATAGOKR_API_KEY`` / the config file)::

        kofia = KOFIA()
        rows = kofia.market_funds(begin="20240101", end="20240131")
    """

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0) -> None:
        self._session = DataGoKrSession(BASE_URL, api_key,
                                        timeout=timeout, json_param="resultType")

    def __repr__(self) -> str:
        return f"KOFIA({self._session!r})"

    @overload
    def market_funds(self, *, begin: str | None = ..., end: str | None = ...,
                     clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def market_funds(self, *, begin: str | None = ..., end: str | None = ...,
                     clean: Literal[False]) -> list[Row]: ...
    @overload
    def market_funds(self, *, begin: str | None = ..., end: str | None = ...,
                     clean: bool) -> list[Row] | list[CleanRow]: ...
    def market_funds(self, *, begin: str | None = None, end: str | None = None,
                     clean: bool = True) -> list[Row] | list[CleanRow]:
        """증시자금추이 -- 일자별 투자자예탁금, 위탁매매미수금, 미수금대비반대매매금액·비중 등.
        ``begin``/``end`` = YYYYMMDD."""
        return self.fetch("market_funds", begin=begin, end=end, clean=clean)

    @overload
    def credit_balance(self, *, begin: str | None = ..., end: str | None = ...,
                       clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def credit_balance(self, *, begin: str | None = ..., end: str | None = ...,
                       clean: Literal[False]) -> list[Row]: ...
    @overload
    def credit_balance(self, *, begin: str | None = ..., end: str | None = ...,
                       clean: bool) -> list[Row] | list[CleanRow]: ...
    def credit_balance(self, *, begin: str | None = None, end: str | None = None,
                       clean: bool = True) -> list[Row] | list[CleanRow]:
        """신용공여잔고추이 -- 일자별 신용거래융자(전체/유가/코스닥), 신용거래대주,
        예탁증권담보융자 등. ``begin``/``end`` = YYYYMMDD."""
        return self.fetch("credit_balance", begin=begin, end=end, clean=clean)

    @overload
    def fetch(self, name: str, *, begin: str | None = ..., end: str | None = ...,
              num_of_rows: int = ..., clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def fetch(self, name: str, *, begin: str | None = ..., end: str | None = ...,
              num_of_rows: int = ..., clean: Literal[False]) -> list[Row]: ...
    @overload
    def fetch(self, name: str, *, begin: str | None = ..., end: str | None = ...,
              num_of_rows: int = ..., clean: bool) -> list[Row] | list[CleanRow]: ...
    def fetch(self, name: str, *, begin: str | None = None, end: str | None = None,
              num_of_rows: int = 1000,
              clean: bool = True) -> list[Row] | list[CleanRow]:
        """Any operation by name (see :meth:`operations`) over an optional date range --
        the path for the six operations without a typed method. Raises ``ValueError`` for an
        unknown ``name``; :class:`~pydatagokr.errors.DataGoKrError` (and subclasses) on a
        transport or vendor failure. ``clean=True`` (the default) returns typed snake_case
        rows; ``clean=False`` the raw vendor rows."""
        try:
            table = TABLES[name]
        except KeyError:
            raise ValueError(f"unknown operation {name!r}; valid: {list(TABLES)}") from None
        rows = self._session.fetch(table.endpoint, num_of_rows=num_of_rows,
                                   **_date_filters(table, begin, end))
        return _spec.clean(rows, table) if clean else rows

    @staticmethod
    def operations() -> tuple[str, ...]:
        """The operation names :meth:`fetch` accepts."""
        return tuple(TABLES)
