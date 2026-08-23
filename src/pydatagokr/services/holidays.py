"""Holidays -- 한국천문연구원 특일 정보 on data.go.kr (service B090041, SpcdeInfoService).

Five operations, one shape: the 공휴일 (`holidays`), 국경일 (`national_holidays`), 기념일
(`anniversaries`), 24절기 (`solar_terms`), and 잡절 (`sundry_days`) of a solar year --
each row a date, its name, and whether it is a public holiday. Every operation carries the
same fields, so one `Table` spec is reused across all five; the vendor tokens (`locdate`,
`isHoliday`) map to clean columns, and `clean=True` (the default) returns typed rows,
`clean=False` the raw vendor rows.

The service answers XML. Pass a `year` (YYYY); `month` (1-12) narrows to one month, else the
whole year is returned.
"""

from __future__ import annotations

from typing import Literal, overload

from .. import _spec
from .._spec import CleanRow, Field, Table
from ..session import DataGoKrSession
from ..types import Row

__all__ = ["AGENCY", "BASE_URL", "Holidays", "SERVICE", "TABLES"]

SERVICE = "holidays"
AGENCY = "한국천문연구원 (Korea Astronomy and Space Science Institute)"
BASE_URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService"

# All five operations share these fields; a special day is keyed by its date and name
# (several may fall on one date).
_FIELDS = (
    Field("locdate",   "date",       "date_ymd", is_key=True),   # 날짜 (YYYYMMDD)
    Field("dateName",  "name",       "text", is_key=True),       # 명칭
    Field("isHoliday", "is_holiday", "text"),                    # 공공기관 휴일 여부 (Y/N)
    Field("dateKind",  "kind_code",  "text"),                    # 종류 코드 (01 공휴일 ...)
    Field("seq",       "sequence",   "int"),                     # 순번
)

HOLIDAYS          = Table("holidays",          "getRestDeInfo",      _FIELDS)
NATIONAL_HOLIDAYS = Table("national_holidays", "getHoliDeInfo",      _FIELDS)
ANNIVERSARIES     = Table("anniversaries",     "getAnniversaryInfo", _FIELDS)
SOLAR_TERMS       = Table("solar_terms",       "get24DivisionsInfo", _FIELDS)
SUNDRY_DAYS       = Table("sundry_days",       "getSundryDayInfo",   _FIELDS)

TABLES: dict[str, Table] = {table.name: table for table in (
    HOLIDAYS, NATIONAL_HOLIDAYS, ANNIVERSARIES, SOLAR_TERMS, SUNDRY_DAYS,
)}


class Holidays:
    """The 특일 정보 surface. Construct with a data.go.kr decoding key (or let it resolve
    ``DATAGOKR_API_KEY`` / the config file)::

        holidays = Holidays()
        rows = holidays.holidays(year=2026)            # 관공서 공휴일
        rows = holidays.fetch("solar_terms", year=2026)  # 24절기
    """

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0) -> None:
        self._session = DataGoKrSession(BASE_URL, api_key,
                                        timeout=timeout, response_format="xml")

    def __repr__(self) -> str:
        return f"Holidays({self._session!r})"

    @overload
    def holidays(self, *, year: int, month: int | None = ...,
                 clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def holidays(self, *, year: int, month: int | None = ...,
                 clean: Literal[False]) -> list[Row]: ...
    @overload
    def holidays(self, *, year: int, month: int | None = ...,
                 clean: bool) -> list[Row] | list[CleanRow]: ...
    def holidays(self, *, year: int, month: int | None = None,
                 clean: bool = True) -> list[Row] | list[CleanRow]:
        """관공서 공휴일 (``getRestDeInfo``) for ``year`` (YYYY); ``month`` (1-12) narrows to
        one month. ``clean=True`` (the default) returns typed rows through
        :data:`HOLIDAYS`; ``clean=False`` the raw vendor rows."""
        return self.fetch("holidays", year=year, month=month, clean=clean)

    @overload
    def fetch(self, name: str, *, year: int, month: int | None = ...,
              clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def fetch(self, name: str, *, year: int, month: int | None = ...,
              clean: Literal[False]) -> list[Row]: ...
    @overload
    def fetch(self, name: str, *, year: int, month: int | None = ...,
              clean: bool) -> list[Row] | list[CleanRow]: ...
    def fetch(self, name: str, *, year: int, month: int | None = None,
              clean: bool = True) -> list[Row] | list[CleanRow]:
        """Any of the five operations by name (see :meth:`operations`) for one solar year,
        optionally one month. Raises ``ValueError`` for an unknown ``name``;
        :class:`~pydatagokr.errors.DataGoKrError` (and subclasses) on a transport or vendor
        failure. ``clean=True`` (the default) returns typed rows; ``clean=False`` the raw
        vendor rows."""
        try:
            table = TABLES[name]
        except KeyError:
            raise ValueError(f"unknown operation {name!r}; valid: {list(TABLES)}") from None
        # num_of_rows is a page size, not a cap: a year has well under 100 special days, so one
        # page fetches them all, and the session's totalCount paging would collect more anyway.
        rows = self._session.fetch(
            table.endpoint, num_of_rows=100,
            solYear=str(year), solMonth=(f"{month:02d}" if month is not None else None))
        return _spec.clean(rows, table) if clean else rows

    @staticmethod
    def operations() -> tuple[str, ...]:
        """The operation names :meth:`fetch` accepts."""
        return tuple(TABLES)
