"""Weather -- 기상청 동네예보 on data.go.kr (service 1360000, VilageFcstInfoService_2.0).

Three operations for one 5km grid cell (``nx``/``ny``): the 단기예보 (`forecast`, to ~3 days),
the 초단기예보 (`ultra_forecast`, to 6 hours), and the 초단기실황 (`nowcast`, the latest
observation). A forecast is a long table -- one row per weather item (``category`` = TMP 기온,
POP 강수확률, SKY 하늘상태, PTY 강수형태, REH 습도, WSD 풍속, ...) per forecast time, its
value in ``forecast_value``; a nowcast carries the same item categories with an
``observed_value``. The value's meaning depends on ``category`` (a temperature, a code, a
percentage), so it is kept as text. ``clean=True`` (the default) returns typed rows,
``clean=False`` the raw vendor rows.

Pass the grid ``nx``/``ny`` and, optionally, the announcement ``base_date`` (YYYYMMDD) /
``base_time`` (HHMM). Omit both to use the latest published announcement for the operation
(the vendor issues the 단기예보 8 times a day, the 초단기 operations hourly). The service
answers XML.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, NamedTuple, overload

from .. import _spec
from .._spec import CleanRow, Field, Table
from ..session import DataGoKrSession
from ..types import Row

__all__ = ["AGENCY", "BASE_URL", "SERVICE", "TABLES", "Weather"]

SERVICE = "weather"
AGENCY = "기상청 (Korea Meteorological Administration)"
BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"

# A forecast row: the announcement (base), the item, the forecast time, and the value.
_FORECAST = (
    Field("baseDate",  "base_date",      "date_ymd"),                # 발표일자
    Field("baseTime",  "base_time",      "text"),                    # 발표시각 (HHMM)
    Field("category",  "category",       "text", is_key=True),       # 예보 항목 (TMP/POP/SKY...)
    Field("fcstDate",  "forecast_date",  "date_ymd", is_key=True),   # 예보일자
    Field("fcstTime",  "forecast_time",  "text", is_key=True),       # 예보시각 (HHMM)
    Field("fcstValue", "forecast_value", "text"),                    # 예보값 (항목별 해석)
    Field("nx",        "nx",             "int", is_key=True),        # 격자 X
    Field("ny",        "ny",             "int", is_key=True),        # 격자 Y
)

# A nowcast row: the same item categories, observed rather than forecast.
_NOWCAST = (
    Field("baseDate",  "base_date",      "date_ymd"),
    Field("baseTime",  "base_time",      "text"),
    Field("category",  "category",       "text", is_key=True),
    Field("obsrValue", "observed_value", "text"),                    # 관측값
    Field("nx",        "nx",             "int", is_key=True),
    Field("ny",        "ny",             "int", is_key=True),
)

FORECAST = Table("forecast", "getVilageFcst", _FORECAST, is_wide_key=True)
ULTRA_FORECAST = Table("ultra_forecast", "getUltraSrtFcst", _FORECAST, is_wide_key=True)
NOWCAST = Table("nowcast", "getUltraSrtNcst", _NOWCAST, is_wide_key=True)

TABLES: dict[str, Table] = {
    table.name: table for table in (FORECAST, ULTRA_FORECAST, NOWCAST)}

_KST = timezone(timedelta(hours=9))  # 한국 표준시 (Korea has no daylight saving)

class _Schedule(NamedTuple):
    """An operation's announcement schedule."""
    slots: tuple[tuple[int, int], ...]   # daily (hour, minute) base_time slots, ascending
    lag_minutes: int                     # safe delay before a slot is actually served


# When base_date/base_time are omitted, pick the latest slot whose announcement is already
# served: ``lag_minutes`` is the vendor's publish delay plus a few minutes' margin, so the
# default never lands on a not-yet-published announcement. The 단기예보 announces 8 times a
# day; the 초단기 operations announce hourly (예보 at HH30, 실황 at HH00).
_SCHEDULE: dict[str, _Schedule] = {
    "forecast":       _Schedule(tuple((hour, 0) for hour in (2, 5, 8, 11, 14, 17, 20, 23)), 15),
    "ultra_forecast": _Schedule(tuple((hour, 30) for hour in range(24)), 20),
    "nowcast":        _Schedule(tuple((hour, 0) for hour in range(24)), 45),
}


def _latest_base(name: str, *, now: datetime | None = None) -> tuple[str, str]:
    """The most recently published ``(base_date, base_time)`` for operation ``name`` as of
    ``now`` (KST). Walks today's slots, then yesterday's, so just after midnight it rolls the
    date back to the previous day's last announcement. ``now`` is injectable for tests; a
    naive value is read as KST wall-clock, a tz-aware value is converted to KST."""
    slots, lag_minutes = _SCHEDULE[name]
    if now is None:
        now = datetime.now(_KST)
    else:
        now = now.replace(tzinfo=_KST) if now.tzinfo is None else now.astimezone(_KST)
    cutoff = now - timedelta(minutes=lag_minutes)
    for day_offset in (0, 1):
        day = (now - timedelta(days=day_offset)).date()
        for hour, minute in reversed(slots):
            issued = datetime(day.year, day.month, day.day, hour, minute, tzinfo=_KST)
            if issued <= cutoff:
                return day.strftime("%Y%m%d"), f"{hour:02d}{minute:02d}"
    raise AssertionError("unreachable: 24h of slots always cover a two-day window")


def _resolve_base(name: str, base_date: str | None,
                  base_time: str | None) -> tuple[str, str]:
    """``base_date``/``base_time`` as given, or -- when both are omitted -- the latest
    published announcement for ``name``. Passing only one, or an empty string, is an error."""
    if base_date is None and base_time is None:
        return _latest_base(name)
    if not base_date or not base_time:
        raise ValueError("pass both base_date and base_time, or neither "
                         "(neither uses the latest published announcement)")
    return base_date, base_time


class Weather:
    """The 동네예보 surface. Construct with a data.go.kr decoding key (or let it resolve
    ``DATAGOKR_API_KEY`` / the config file)::

        weather = Weather()
        rows = weather.forecast(nx=60, ny=127)   # latest announcement; or pass base_date/base_time
    """

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0) -> None:
        self._session = DataGoKrSession(BASE_URL, api_key,
                                        timeout=timeout, response_format="xml")

    def __repr__(self) -> str:
        return f"Weather({self._session!r})"

    @overload
    def forecast(self, *, base_date: str | None = ..., base_time: str | None = ...,
                 nx: int, ny: int, clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def forecast(self, *, base_date: str | None = ..., base_time: str | None = ...,
                 nx: int, ny: int, clean: Literal[False]) -> list[Row]: ...
    @overload
    def forecast(self, *, base_date: str | None = ..., base_time: str | None = ...,
                 nx: int, ny: int, clean: bool) -> list[Row] | list[CleanRow]: ...
    def forecast(self, *, base_date: str | None = None, base_time: str | None = None,
                 nx: int, ny: int, clean: bool = True) -> list[Row] | list[CleanRow]:
        """단기예보 (``getVilageFcst``), to ~3 days, for the grid cell ``nx``/``ny`` at the
        ``base_date``/``base_time`` announcement. Args as :meth:`fetch`."""
        return self.fetch("forecast", base_date=base_date, base_time=base_time,
                          nx=nx, ny=ny, clean=clean)

    @overload
    def ultra_forecast(self, *, base_date: str | None = ..., base_time: str | None = ...,
                       nx: int, ny: int, clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def ultra_forecast(self, *, base_date: str | None = ..., base_time: str | None = ...,
                       nx: int, ny: int, clean: Literal[False]) -> list[Row]: ...
    @overload
    def ultra_forecast(self, *, base_date: str | None = ..., base_time: str | None = ...,
                       nx: int, ny: int, clean: bool) -> list[Row] | list[CleanRow]: ...
    def ultra_forecast(self, *, base_date: str | None = None, base_time: str | None = None,
                       nx: int, ny: int, clean: bool = True) -> list[Row] | list[CleanRow]:
        """초단기예보 (``getUltraSrtFcst``), to 6 hours. Args as :meth:`fetch`."""
        return self.fetch("ultra_forecast", base_date=base_date, base_time=base_time,
                          nx=nx, ny=ny, clean=clean)

    @overload
    def nowcast(self, *, base_date: str | None = ..., base_time: str | None = ...,
                nx: int, ny: int, clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def nowcast(self, *, base_date: str | None = ..., base_time: str | None = ...,
                nx: int, ny: int, clean: Literal[False]) -> list[Row]: ...
    @overload
    def nowcast(self, *, base_date: str | None = ..., base_time: str | None = ...,
                nx: int, ny: int, clean: bool) -> list[Row] | list[CleanRow]: ...
    def nowcast(self, *, base_date: str | None = None, base_time: str | None = None,
                nx: int, ny: int, clean: bool = True) -> list[Row] | list[CleanRow]:
        """초단기실황 (``getUltraSrtNcst``), the latest observation. Args as :meth:`fetch`."""
        return self.fetch("nowcast", base_date=base_date, base_time=base_time,
                          nx=nx, ny=ny, clean=clean)

    @overload
    def fetch(self, name: str, *, base_date: str | None = ..., base_time: str | None = ...,
              nx: int, ny: int, clean: Literal[True] = ...) -> list[CleanRow]: ...
    @overload
    def fetch(self, name: str, *, base_date: str | None = ..., base_time: str | None = ...,
              nx: int, ny: int, clean: Literal[False]) -> list[Row]: ...
    @overload
    def fetch(self, name: str, *, base_date: str | None = ..., base_time: str | None = ...,
              nx: int, ny: int, clean: bool) -> list[Row] | list[CleanRow]: ...
    def fetch(self, name: str, *, base_date: str | None = None, base_time: str | None = None,
              nx: int, ny: int, clean: bool = True) -> list[Row] | list[CleanRow]:
        """Any of the three operations by name (see :meth:`operations`) for one grid cell.
        ``base_date`` = YYYYMMDD, ``base_time`` = HHMM (the announcement time), ``nx``/``ny``
        the 기상청 5km grid. Omit both ``base_date`` and ``base_time`` (or pass neither) to use
        the latest published announcement for this operation. Raises ``ValueError`` for an
        unknown ``name`` (or a lone ``base_date``/``base_time``);
        :class:`~pydatagokr.errors.DataGoKrError` (and subclasses) on a transport or vendor
        failure. ``clean=True`` (the default) returns typed rows; ``clean=False`` raw."""
        try:
            table = TABLES[name]
        except KeyError:
            raise ValueError(f"unknown operation {name!r}; valid: {list(TABLES)}") from None
        base_date, base_time = _resolve_base(name, base_date, base_time)
        rows = self._session.fetch(table.endpoint, base_date=base_date, base_time=base_time,
                                   nx=str(nx), ny=str(ny))
        return _spec.clean(rows, table) if clean else rows

    @staticmethod
    def operations() -> tuple[str, ...]:
        """The operation names :meth:`fetch` accepts."""
        return tuple(TABLES)
