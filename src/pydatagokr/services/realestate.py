"""RealEstate -- 국토교통부 아파트 실거래가 on data.go.kr (service 1613000, RTMS).

Four sibling services under one org, grouped as one surface: 아파트 매매 (`apt_trade`),
매매 상세 (`apt_trade_detail`, adds the road address), 전월세 (`apt_rent`), and 분양권전매
(`apt_presale`). Each row is one transaction for a 법정동 (``lawd_code`` = the 5-digit
법정동 시군구코드, ``LAWD_CD``) and a 계약년월 (``deal_ym`` = YYYYMM, ``DEAL_YMD``). The
vendor's split year/month/day is combined into a single ``deal_date`` (ISO); amounts are in
만원 as the vendor reports them (거래금액·보증금·월세). ``clean=True`` (the default) returns
typed rows, ``clean=False`` the raw vendor rows.

The four operations are separate services under ``/1613000``, so each table's operation path
carries its service segment (``RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade``) and one session
at the org root reaches all four. The service answers XML.
"""

from __future__ import annotations

from typing import Literal, overload

from .. import _spec
from .._spec import CleanRow, Field, Table
from ..session import DataGoKrSession
from ..types import Row

__all__ = ["AGENCY", "BASE_URL", "RealEstate", "SERVICE", "TABLES"]

SERVICE = "realestate"
AGENCY = "국토교통부 (Ministry of Land, Infrastructure and Transport)"
BASE_URL = "https://apis.data.go.kr/1613000"

# Fields common to the sale-type operations (매매·매매상세·분양권). ``deal_date`` is
# synthesized from the vendor's dealYear/dealMonth/dealDay before cleaning (see _deal_date).
_SALE_CORE = (
    Field("dealDate",        "deal_date",       "date_ymd", is_key=True),   # 계약일
    Field("sggCd",           "lawd_code",       "text", is_key=True),       # 법정동 시군구코드
    Field("umdNm",           "dong",            "text", is_key=True),       # 법정동명
    Field("jibun",           "jibun",           "text", is_key=True),       # 지번
    Field("aptNm",           "apt_name",        "text", is_key=True),       # 단지명
    Field("excluUseAr",      "exclusive_area",  "decimal", is_key=True),    # 전용면적(m^2)
    Field("floor",           "floor",           "int", is_key=True),        # 층
    Field("buildYear",       "build_year",      "int"),                     # 건축년도
    Field("dealAmount",      "deal_amount",     "int"),                     # 거래금액(만원)
    Field("dealingGbn",      "dealing_type",    "text"),                    # 거래유형(중개/직거래)
    Field("buyerGbn",        "buyer_type",      "text"),                    # 매수자 구분
    Field("slerGbn",         "seller_type",     "text"),                    # 매도자 구분
    Field("cdealType",       "cancel_type",     "text"),                    # 해제여부
    Field("cdealDay",        "cancel_date",     "text"),                    # 해제사유발생일
    Field("estateAgentSggNm", "agent_region",   "text"),                    # 중개사 소재지
)

APT_TRADE = Table("apt_trade", "RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
                  _SALE_CORE + (
    Field("aptDong",         "apt_dong",        "text"),                    # 동
    Field("landLeaseholdGbn", "land_leasehold", "text"),                   # 토지임대부 여부
    Field("rgstDate",        "register_date",   "text"),                    # 등기일자
), is_wide_key=True)

APT_TRADE_DETAIL = Table(
    "apt_trade_detail", "RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    _SALE_CORE + (
    Field("aptDong",         "apt_dong",        "text"),
    Field("aptSeq",          "apt_seq",         "text"),                    # 단지 일련번호
    Field("bonbun",          "main_no",         "text"),                    # 본번
    Field("bubun",           "sub_no",          "text"),                    # 부번
    Field("landCd",          "land_code",       "text"),                    # 지역코드
    Field("landLeaseholdGbn", "land_leasehold", "text"),
    Field("umdCd",           "dong_code",       "text"),                    # 법정동 읍면동코드
    Field("rgstDate",        "register_date",   "text"),
    Field("roadNm",          "road_name",       "text"),                    # 도로명
    Field("roadNmCd",        "road_code",       "text"),
    Field("roadNmBonbun",    "road_main_no",    "text"),
    Field("roadNmBubun",     "road_sub_no",     "text"),
    Field("roadNmSeq",       "road_seq",        "text"),
    Field("roadNmSggCd",     "road_sgg_code",   "text"),
    Field("roadNmbCd",       "road_basement_yn", "text"),
), is_wide_key=True)

APT_PRESALE = Table("apt_presale", "RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade",
                    _SALE_CORE + (
    Field("ownershipGbn",    "ownership_type",  "text"),                    # 권리구분(분양/입주권)
    Field("sggNm",           "sgg_name",        "text"),                    # 시군구명
), is_wide_key=True)

APT_RENT = Table("apt_rent", "RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
                 (
    Field("dealDate",        "deal_date",          "date_ymd", is_key=True),
    Field("sggCd",           "lawd_code",          "text", is_key=True),
    Field("umdNm",           "dong",               "text", is_key=True),
    Field("jibun",           "jibun",              "text", is_key=True),
    Field("aptNm",           "apt_name",           "text", is_key=True),
    Field("excluUseAr",      "exclusive_area",     "decimal", is_key=True),
    Field("floor",           "floor",              "int", is_key=True),
    Field("buildYear",       "build_year",         "int"),
    Field("deposit",         "deposit",            "int"),                       # 보증금(만원)
    Field("monthlyRent",     "monthly_rent",       "int"),                       # 월세(만원)
    Field("contractType",    "contract_type",      "text"),                      # 신규/갱신
    Field("contractTerm",    "contract_term",      "text"),                      # 계약기간
    Field("preDeposit",      "prev_deposit",       "int"),                       # 종전 보증금(만원)
    Field("preMonthlyRent",  "prev_monthly_rent",  "int"),                       # 종전 월세(만원)
    Field("useRRRight",      "renewal_right_used", "text"),                      # 갱신요구권 사용
    Field("aptSeq",          "apt_seq",            "text"),
    Field("roadnm",          "road_name",          "text"),
    Field("roadnmcd",        "road_code",          "text"),
    Field("roadnmbonbun",    "road_main_no",       "text"),
    Field("roadnmbubun",     "road_sub_no",        "text"),
    Field("roadnmseq",       "road_seq",           "text"),
    Field("roadnmsggcd",     "road_sgg_code",      "text"),
    Field("roadnmbcd",       "road_basement_yn",   "text"),
), is_wide_key=True)

TABLES: dict[str, Table] = {table.name: table for table in (
    APT_TRADE, APT_TRADE_DETAIL, APT_RENT, APT_PRESALE,
)}


def _deal_date(row: Row) -> str:
    """YYYYMMDD from the vendor's dealYear/dealMonth/dealDay (empty when any is missing);
    :func:`_spec.clean` then parses it to an ISO date, dropping a row with no valid date."""
    year, month, day = row.get("dealYear"), row.get("dealMonth"), row.get("dealDay")
    if not (year and month and day):
        return ""
    try:
        y, m, d = int(year), int(month), int(day)
    except (TypeError, ValueError):
        # A non-numeric part (a malformed vendor value) yields no date, so _spec.clean
        # drops just this row on its date_ymd required-check -- one poisoned row does not
        # crash the whole fetch.
        return ""
    if y < 1000:
        # A 2-digit dealYear ("24") would format to "0024..." and strptime to a silently
        # wrong ISO date; RTMS sends a 4-digit year, so treat a short year as malformed and
        # let the row drop on its required date check rather than emit a wrong date.
        return ""
    return f"{y:04d}{m:02d}{d:02d}"


class RealEstate:
    """The 아파트 실거래가 surface. Construct with a data.go.kr decoding key (or let it
    resolve ``DATAGOKR_API_KEY`` / the config file)::

        re = RealEstate()
        rows = re.apt_trade(lawd_code="11110", deal_ym="202401")   # 종로구 2024-01 매매
        rows = re.apt_rent(lawd_code="11110", deal_ym="202401")    # 전월세
    """

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0) -> None:
        self._session = DataGoKrSession(BASE_URL, api_key,
                                        timeout=timeout, response_format="xml")

    def __repr__(self) -> str:
        return f"RealEstate({self._session!r})"

    @overload
    def apt_trade(self, *, lawd_code: str, deal_ym: str,
                  clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def apt_trade(self, *, lawd_code: str, deal_ym: str,
                  clean: Literal[False]) -> list[Row]: ...
    @overload
    def apt_trade(self, *, lawd_code: str, deal_ym: str,
                  clean: bool) -> list[Row] | list[CleanRow]: ...
    def apt_trade(self, *, lawd_code: str, deal_ym: str,
                  clean: bool = True) -> list[Row] | list[CleanRow]:
        """아파트 매매 실거래가 for one 법정동 (``lawd_code``) and 계약년월 (``deal_ym`` =
        YYYYMM). ``clean=True`` (the default) returns typed rows; ``clean=False`` raw."""
        return self.fetch("apt_trade", lawd_code=lawd_code, deal_ym=deal_ym, clean=clean)

    @overload
    def apt_trade_detail(self, *, lawd_code: str, deal_ym: str,
                         clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def apt_trade_detail(self, *, lawd_code: str, deal_ym: str,
                         clean: Literal[False]) -> list[Row]: ...
    @overload
    def apt_trade_detail(self, *, lawd_code: str, deal_ym: str,
                         clean: bool) -> list[Row] | list[CleanRow]: ...
    def apt_trade_detail(self, *, lawd_code: str, deal_ym: str,
                         clean: bool = True) -> list[Row] | list[CleanRow]:
        """아파트 매매 실거래가 상세 (adds the road address). Args as :meth:`apt_trade`."""
        return self.fetch("apt_trade_detail", lawd_code=lawd_code, deal_ym=deal_ym,
                          clean=clean)

    @overload
    def apt_rent(self, *, lawd_code: str, deal_ym: str,
                 clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def apt_rent(self, *, lawd_code: str, deal_ym: str,
                 clean: Literal[False]) -> list[Row]: ...
    @overload
    def apt_rent(self, *, lawd_code: str, deal_ym: str,
                 clean: bool) -> list[Row] | list[CleanRow]: ...
    def apt_rent(self, *, lawd_code: str, deal_ym: str,
                 clean: bool = True) -> list[Row] | list[CleanRow]:
        """아파트 전월세 실거래가 (보증금·월세). Args as :meth:`apt_trade`."""
        return self.fetch("apt_rent", lawd_code=lawd_code, deal_ym=deal_ym, clean=clean)

    @overload
    def apt_presale(self, *, lawd_code: str, deal_ym: str,
                    clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def apt_presale(self, *, lawd_code: str, deal_ym: str,
                    clean: Literal[False]) -> list[Row]: ...
    @overload
    def apt_presale(self, *, lawd_code: str, deal_ym: str,
                    clean: bool) -> list[Row] | list[CleanRow]: ...
    def apt_presale(self, *, lawd_code: str, deal_ym: str,
                    clean: bool = True) -> list[Row] | list[CleanRow]:
        """아파트 분양권전매 실거래가. Args as :meth:`apt_trade`."""
        return self.fetch("apt_presale", lawd_code=lawd_code, deal_ym=deal_ym, clean=clean)

    @overload
    def fetch(self, name: str, *, lawd_code: str, deal_ym: str,
              clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def fetch(self, name: str, *, lawd_code: str, deal_ym: str,
              clean: Literal[False]) -> list[Row]: ...
    @overload
    def fetch(self, name: str, *, lawd_code: str, deal_ym: str,
              clean: bool) -> list[Row] | list[CleanRow]: ...
    def fetch(self, name: str, *, lawd_code: str, deal_ym: str,
              clean: bool = True) -> list[Row] | list[CleanRow]:
        """Any of the four operations by name (see :meth:`operations`) for one 법정동 and
        계약년월. Raises ``ValueError`` for an unknown ``name``;
        :class:`~pydatagokr.errors.DataGoKrError` (and subclasses) on a transport or vendor
        failure. ``clean=True`` (the default) returns typed rows; ``clean=False`` raw."""
        try:
            table = TABLES[name]
        except KeyError:
            raise ValueError(f"unknown operation {name!r}; valid: {list(TABLES)}") from None
        rows = self._session.fetch(table.endpoint, LAWD_CD=lawd_code, DEAL_YMD=deal_ym)
        if not clean:
            return rows
        for row in rows:
            row["dealDate"] = _deal_date(row)
        return _spec.clean(rows, table)

    @staticmethod
    def operations() -> tuple[str, ...]:
        """The operation names :meth:`fetch` accepts."""
        return tuple(TABLES)
