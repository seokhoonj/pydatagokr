"""AirQuality -- 한국환경공단 에어코리아 대기오염정보 on data.go.kr (service B552584).

Real-time air-quality measurements, two ways: `by_sido` (getCtprvnRltmMesureDnsty -- every
station in a 시도 at the latest time) and `by_station` (getMsrstnAcctoRltmMesureDnsty -- one
station over a term). Each row carries the 통합대기환경지수 (`khai`) and the six pollutants
-- 미세먼지 `pm10`, 초미세먼지 `pm25` (both integers, ㎍/㎥) and 아황산가스 `so2`, 일산화탄소
`co`, 오존 `o3`, 이산화질소 `no2` (decimals, ppm) -- each with its `_grade` (1 좋음 · 2 보통 ·
3 나쁨 · 4 매우나쁨) and a `_flag` (a message when the value is unavailable). ``clean=True``
(the default) returns typed rows, ``clean=False`` the raw vendor rows. The service answers XML.
"""

from __future__ import annotations

from typing import Literal, overload

from .. import _spec
from .._spec import CleanRow, Field, Table
from ..session import DataGoKrSession
from ..types import Row

__all__ = ["AGENCY", "AirQuality", "AirVersion", "BASE_URL", "DataTerm", "SERVICE", "TABLES"]

SERVICE = "airquality"
AGENCY = "한국환경공단 (Korea Environment Corporation, AirKorea)"
BASE_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc"

# The measurement window ``by_station`` accepts as ``dataTerm`` -- a closed three-value set.
DataTerm = Literal["DAILY", "MONTH", "3MONTH"]

# The response version ``ver`` selects -- a closed set: 1.0 adds PM2.5 (the default here),
# up to 1.3 which adds the 1-hour grades. Typed like ``DataTerm`` so a wrong version is a
# call-site type error rather than a vendor fault, symmetric with its sibling parameter.
AirVersion = Literal["1.0", "1.1", "1.2", "1.3"]

# The measurement columns, shared by both operations.
_MEASURE = (
    Field("dataTime",  "measured_at", "text", is_key=True),   # 측정일시
    Field("khaiValue", "khai",        "int"),    Field("khaiGrade", "khai_grade", "int"),
    Field("pm10Value", "pm10",        "int"),    Field("pm10Grade", "pm10_grade", "int"),
    Field("pm10Flag",  "pm10_flag",   "text"),
    Field("pm25Value", "pm25",        "int"),    Field("pm25Grade", "pm25_grade", "int"),
    Field("pm25Flag",  "pm25_flag",   "text"),
    Field("so2Value",  "so2",         "decimal"), Field("so2Grade", "so2_grade", "int"),
    Field("so2Flag",   "so2_flag",    "text"),
    Field("coValue",   "co",          "decimal"), Field("coGrade",  "co_grade",  "int"),
    Field("coFlag",    "co_flag",     "text"),
    Field("o3Value",   "o3",          "decimal"), Field("o3Grade",  "o3_grade",  "int"),
    Field("o3Flag",    "o3_flag",     "text"),
    Field("no2Value",  "no2",         "decimal"), Field("no2Grade", "no2_grade", "int"),
    Field("no2Flag",   "no2_flag",    "text"),
)

BY_SIDO = Table("by_sido", "getCtprvnRltmMesureDnsty", (
    Field("sidoName",    "sido",    "text"),                    # 시도명
    Field("stationName", "station", "text", is_key=True),       # 측정소명
) + _MEASURE, is_wide_key=True)

BY_STATION = Table("by_station", "getMsrstnAcctoRltmMesureDnsty", (
    Field("mangName",    "network", "text"),                    # 측정망 (도시대기 ...)
    Field("stationName", "station", "text", is_key=True),       # 측정소명
) + _MEASURE, is_wide_key=True)

TABLES: dict[str, Table] = {BY_SIDO.name: BY_SIDO, BY_STATION.name: BY_STATION}


class AirQuality:
    """The 에어코리아 대기오염정보 surface. Construct with a data.go.kr decoding key (or let
    it resolve ``DATAGOKR_API_KEY`` / the config file)::

        air = AirQuality()
        rows = air.by_sido(sido="서울")          # 서울 전 측정소 최신값
        rows = air.by_station(station="종로구")   # 한 측정소의 하루치
    """

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0) -> None:
        self._session = DataGoKrSession(BASE_URL, api_key,
                                        timeout=timeout, response_format="xml")

    def __repr__(self) -> str:
        return f"AirQuality({self._session!r})"

    @overload
    def by_sido(self, *, sido: str, ver: AirVersion = ...,
                clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def by_sido(self, *, sido: str, ver: AirVersion = ...,
                clean: Literal[False]) -> list[Row]: ...
    @overload
    def by_sido(self, *, sido: str, ver: AirVersion = ...,
                clean: bool) -> list[Row] | list[CleanRow]: ...
    def by_sido(self, *, sido: str, ver: AirVersion = "1.0",
                clean: bool = True) -> list[Row] | list[CleanRow]:
        """시도별 실시간 측정정보 (``getCtprvnRltmMesureDnsty``) -- every station in ``sido``
        (서울/부산/경기/...) at the latest time. ``clean=True`` (the default) returns typed
        rows; ``clean=False`` raw."""
        rows = self._session.fetch(BY_SIDO.endpoint, sidoName=sido, ver=ver)
        return _spec.clean(rows, BY_SIDO) if clean else rows

    @overload
    def by_station(self, *, station: str, data_term: DataTerm = ..., ver: AirVersion = ...,
                   clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def by_station(self, *, station: str, data_term: DataTerm = ..., ver: AirVersion = ...,
                   clean: Literal[False]) -> list[Row]: ...
    @overload
    def by_station(self, *, station: str, data_term: DataTerm = ..., ver: AirVersion = ...,
                   clean: bool) -> list[Row] | list[CleanRow]: ...
    def by_station(self, *, station: str, data_term: DataTerm = "DAILY", ver: AirVersion = "1.0",
                   clean: bool = True) -> list[Row] | list[CleanRow]:
        """측정소별 실시간 측정정보 (``getMsrstnAcctoRltmMesureDnsty``) for one ``station``
        over ``data_term`` (``DAILY`` / ``MONTH`` / ``3MONTH``). ``clean`` as
        :meth:`by_sido`."""
        rows = self._session.fetch(BY_STATION.endpoint, stationName=station,
                                   dataTerm=data_term, ver=ver)
        return _spec.clean(rows, BY_STATION) if clean else rows

    @staticmethod
    def operations() -> tuple[str, ...]:
        """The operation names this surface exposes."""
        return tuple(TABLES)
