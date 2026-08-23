"""DataGoKr -- the entry point.

Built from one data.go.kr service key (constructor, ``DATAGOKR_API_KEY`` env, or the
config file), it exposes the wrapped services as lazy sub-surfaces -- ``weather``,
``airquality``, ``holidays``, ``realestate``, ``midforecast``, ``procurement``,
``customs``, and ``kofia`` -- each holding its own
:class:`~pydatagokr.session.DataGoKrSession` built with the same key and timeout. A
surface is constructed on first access (``@cached_property``), so building ``DataGoKr()``
itself needs no key at all.
"""

from __future__ import annotations

from functools import cached_property

from .services.airquality import AirQuality
from .services.customs import Customs
from .services.holidays import Holidays
from .services.kofia import KOFIA
from .services.midforecast import MidForecast
from .services.procurement import Procurement
from .services.realestate import RealEstate
from .services.weather import Weather

__all__ = ["DataGoKr"]


class DataGoKr:
    """Client for the wrapped data.go.kr services. Groups them as sub-surfaces::

        client = DataGoKr()                    # or set DATAGOKR_API_KEY
        rows  = client.kofia.market_funds(begin="20240101", end="20240131")
        trade = client.customs.item_trade("8542", start="202401", end="202406")

    One data.go.kr account key serves every dataset it has applied for (활용신청); a call
    to one not yet approved raises :class:`~pydatagokr.errors.DataGoKrAuthError`.

    **Thread safety.** A ``DataGoKr``, its service surfaces, and their sessions hold no
    per-request mutable state (the key and config are set once at construction, each request
    uses only locals, and the shared opener makes a fresh connection per call), so one client
    may be shared across threads for concurrent fetches. The one caveat: on Python 3.12+ the
    first concurrent access to a service accessor may build it twice, harmlessly (both are
    equivalent); touch the accessors once before fanning out if that matters.
    """

    _api_key: str | None
    _timeout: float

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def __repr__(self) -> str:
        # Never shows the service key, in whole or in part.
        return "DataGoKr(...)"

    @cached_property
    def kofia(self) -> KOFIA:
        """금융투자협회 (KOFIA) 종합통계 -- 예탁금, 신용잔고, 펀드, CMA, ELS/DLS, 신탁,
        해외파생."""
        return KOFIA(self._api_key, timeout=self._timeout)

    @cached_property
    def customs(self) -> Customs:
        """관세청 수출입 무역통계 -- 품목별(HS) 수출입실적."""
        return Customs(self._api_key, timeout=self._timeout)

    @cached_property
    def holidays(self) -> Holidays:
        """한국천문연구원 특일 정보 -- 공휴일·국경일·기념일·24절기·잡절."""
        return Holidays(self._api_key, timeout=self._timeout)

    @cached_property
    def realestate(self) -> RealEstate:
        """국토교통부 아파트 실거래가 -- 매매·매매상세·전월세·분양권전매."""
        return RealEstate(self._api_key, timeout=self._timeout)

    @cached_property
    def weather(self) -> Weather:
        """기상청 동네예보 -- 단기예보·초단기예보·초단기실황(격자별)."""
        return Weather(self._api_key, timeout=self._timeout)

    @cached_property
    def airquality(self) -> AirQuality:
        """한국환경공단 에어코리아 대기오염정보 -- 시도별·측정소별 실시간 측정."""
        return AirQuality(self._api_key, timeout=self._timeout)

    @cached_property
    def midforecast(self) -> MidForecast:
        """기상청 중기예보 -- 예보구역별 4~10일 육상(강수·날씨)·기온(최저·최고)."""
        return MidForecast(self._api_key, timeout=self._timeout)

    @cached_property
    def procurement(self) -> Procurement:
        """조달청 나라장터 입찰공고 -- 물품·용역·공사·외자 업무구분별."""
        return Procurement(self._api_key, timeout=self._timeout)
