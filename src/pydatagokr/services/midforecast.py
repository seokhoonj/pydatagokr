"""MidForecast -- 기상청 중기예보 on data.go.kr (service 1360000, MidFcstInfoService).

The 3-to-10-day outlook for a forecast region, two ways: `land` (getMidLandFcst -- 강수확률
`precip_prob_*` and a sky-state phrase `sky_*` for each half-day) and `temperature`
(getMidTa -- daily 최저·최고기온 `temp_min_*`/`temp_max_*`). Where 단기예보 (the `weather`
surface) forecasts the next ~3 days on a 5km grid, 중기예보 covers days 4-10 for a coarser
예보구역 named by a ``regid`` (``11B00000`` 서울/인천/경기 for land, ``11B10101`` 서울
for temperature -- see the 기상청 예보구역 code table).

The rows are **wide**: one row per region, a column per forecast day. Days 4-7 split into
morning/afternoon (``_4am``/``_4pm`` .. ``_7am``/``_7pm``); days 8-10 are single (``_8``
..``_10``). Which days a call returns depends on ``time_forecast`` -- the 0600 announcement
reaches day 4, the 1800 announcement starts at day 5 -- so a day the announcement does not
cover is simply absent (its columns ``None``). ``clean=True`` (the default) returns typed
rows, ``clean=False`` the raw vendor rows. The service answers XML.
"""

from __future__ import annotations

from typing import Literal, overload

from .. import _spec
from .._spec import CleanRow, Field, Table
from ..session import DataGoKrSession
from ..types import Row

__all__ = ["AGENCY", "BASE_URL", "MidForecast", "SERVICE", "TABLES"]

SERVICE = "midforecast"
AGENCY = "기상청 (Korea Meteorological Administration)"
BASE_URL = "https://apis.data.go.kr/1360000/MidFcstInfoService"


def _half_day_fields(token: str, column: str, kind: _spec.FieldKind) -> tuple[Field, ...]:
    """The wide day-columns for one measure: 4am/4pm .. 7am/7pm then 8/9/10. The vendor
    names them ``<token>{4..7}{Am,Pm}`` and ``<token>{8..10}`` (e.g. ``rnSt5Am``, ``wf8``);
    the clean column mirrors the shape as ``<column>_{4..7}{am,pm}`` / ``<column>_{8..10}``."""
    fields = []
    for day in (4, 5, 6, 7):
        for part in ("Am", "Pm"):
            fields.append(Field(f"{token}{day}{part}",
                                f"{column}_{day}{part.lower()}", kind))
    for day in (8, 9, 10):
        fields.append(Field(f"{token}{day}", f"{column}_{day}", kind))
    return tuple(fields)


LAND = Table("land", "getMidLandFcst", (
    Field("regId", "regid", "text", is_key=True),               # 예보구역코드
) + _half_day_fields("rnSt", "precip_prob", "int")               # 강수확률(%)
  + _half_day_fields("wf", "sky", "text"), is_wide_key=True)     # 날씨(하늘상태 문구)

TEMPERATURE = Table("temperature", "getMidTa", (
    Field("regId", "regid", "text", is_key=True),               # 예보구역코드(도시)
) + tuple(
    field
    for day in (4, 5, 6, 7, 8, 9, 10)
    for field in (Field(f"taMin{day}", f"temp_min_{day}", "int"),   # 최저기온
                  Field(f"taMax{day}", f"temp_max_{day}", "int"))   # 최고기온
), is_wide_key=True)

TABLES: dict[str, Table] = {LAND.name: LAND, TEMPERATURE.name: TEMPERATURE}


class MidForecast:
    """The 중기예보 surface. Construct with a data.go.kr decoding key (or let it resolve
    ``DATAGOKR_API_KEY`` / the config file)::

        mid = MidForecast()
        rows = mid.land(regid="11B00000", time_forecast="202608111800")        # 육상(강수·날씨)
        rows = mid.temperature(regid="11B10101", time_forecast="202608111800") # 기온(최저·최고)
    """

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0) -> None:
        self._session = DataGoKrSession(BASE_URL, api_key,
                                        timeout=timeout, response_format="xml")

    def __repr__(self) -> str:
        return f"MidForecast({self._session!r})"

    @overload
    def land(self, *, regid: str, time_forecast: str,
             clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def land(self, *, regid: str, time_forecast: str,
             clean: Literal[False]) -> list[Row]: ...
    @overload
    def land(self, *, regid: str, time_forecast: str,
             clean: bool) -> list[Row] | list[CleanRow]: ...
    def land(self, *, regid: str, time_forecast: str,
             clean: bool = True) -> list[Row] | list[CleanRow]:
        """중기육상예보 (``getMidLandFcst``) -- 강수확률·날씨 for ``regid`` (a 예보구역코드
        such as ``11B00000``) announced at ``time_forecast`` (YYYYMMDDHHMM, the 0600 or 1800
        발표시각). ``clean=True`` (the default) returns typed rows; ``clean=False`` raw."""
        return self.fetch("land", regid=regid, time_forecast=time_forecast, clean=clean)

    @overload
    def temperature(self, *, regid: str, time_forecast: str,
                    clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def temperature(self, *, regid: str, time_forecast: str,
                    clean: Literal[False]) -> list[Row]: ...
    @overload
    def temperature(self, *, regid: str, time_forecast: str,
                    clean: bool) -> list[Row] | list[CleanRow]: ...
    def temperature(self, *, regid: str, time_forecast: str,
                    clean: bool = True) -> list[Row] | list[CleanRow]:
        """중기기온예보 (``getMidTa``) -- daily 최저·최고기온 for ``regid`` (a 도시 예보구역
        코드 such as ``11B10101``). Args as :meth:`land`."""
        return self.fetch("temperature", regid=regid, time_forecast=time_forecast, clean=clean)

    @overload
    def fetch(self, name: str, *, regid: str, time_forecast: str,
              clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def fetch(self, name: str, *, regid: str, time_forecast: str,
              clean: Literal[False]) -> list[Row]: ...
    @overload
    def fetch(self, name: str, *, regid: str, time_forecast: str,
              clean: bool) -> list[Row] | list[CleanRow]: ...
    def fetch(self, name: str, *, regid: str, time_forecast: str,
              clean: bool = True) -> list[Row] | list[CleanRow]:
        """Either operation by name (``land`` / ``temperature``) for one ``regid`` and
        ``time_forecast``. A ``regid`` is a 예보구역 REGID -- resolve one from a place name
        with :func:`~pydatagokr.land_region` / :func:`~pydatagokr.temp_region` (CLI:
        ``datagokr land-region`` / ``temp-region``). Raises ``ValueError`` for an unknown
        ``name``; :class:`~pydatagokr.errors.DataGoKrError` (and subclasses) on a transport or
        vendor failure. ``clean=True`` (the default) returns typed rows; ``clean=False`` raw."""
        try:
            table = TABLES[name]
        except KeyError:
            raise ValueError(f"unknown operation {name!r}; valid: {list(TABLES)}") from None
        rows = self._session.fetch(table.endpoint, dataType="XML",
                                   regId=regid, tmFc=time_forecast)
        return _spec.clean(rows, table) if clean else rows

    @staticmethod
    def operations() -> tuple[str, ...]:
        """The operation names :meth:`fetch` accepts."""
        return tuple(TABLES)
