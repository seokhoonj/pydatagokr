"""pydatagokr -- read Korean government open-data services from data.go.kr.

    from pydatagokr import DataGoKr

    client = DataGoKr()                    # or set DATAGOKR_API_KEY (the *decoding* key)
    rows   = client.weather.forecast(base_date="20260811", base_time="0500", nx=60, ny=127)
    trades = client.realestate.apt_trade(lawd_code="11110", deal_ym="202401")

One key, many services: the shared :class:`DataGoKrSession` speaks the portal's common
envelope and paging protocol, and each wrapped agency -- 기상청 동네예보, 에어코리아 대기오염,
국토교통부 아파트 실거래가, ... -- is a thin surface over it. Rows come back as ``list[dict]``
with the vendor's own field names (or cleaned to typed snake_case columns via the
per-operation table specs) -- frame them your own way, e.g. ``pandas.DataFrame(rows)`` or
``polars.DataFrame(rows)``. The offline :mod:`pydatagokr.catalog` lists every service and
operation without a call.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from . import catalog
from ._spec import CleanRow, CleanValue, Field, FieldKind, Table, clean
from .client import DataGoKr
from .errors import (
    DataGoKrAuthError,
    DataGoKrConfigError,
    DataGoKrError,
    DataGoKrNetworkError,
    DataGoKrPagingError,
    DataGoKrRateLimitError,
    DataGoKrResponseError,
)
from .grid import Grid, latlon_to_grid
from .regions import land_region, lawd_code, temp_region
from .services import (
    KOFIA,
    AirQuality,
    Customs,
    Holidays,
    MidForecast,
    Procurement,
    RealEstate,
    Weather,
)
from .services.airquality import AirVersion, DataTerm
from .services.procurement import QueryBasis
from .session import DataGoKrSession
from .types import JSONParam, ResponseFormat, Row

try:
    __version__ = version("pydatagokr")   # single source of truth: pyproject.toml
except PackageNotFoundError:              # running from source without an install
    __version__ = "0.0.0+unknown"

__all__ = [
    "AirQuality",
    "AirVersion",
    "CleanRow",
    "CleanValue",
    "Customs",
    "DataGoKr",
    "DataGoKrAuthError",
    "DataGoKrConfigError",
    "DataGoKrError",
    "DataGoKrNetworkError",
    "DataGoKrPagingError",
    "DataGoKrRateLimitError",
    "DataGoKrResponseError",
    "DataGoKrSession",
    "DataTerm",
    "Field",
    "FieldKind",
    "Grid",
    "Holidays",
    "JSONParam",
    "KOFIA",
    "MidForecast",
    "Procurement",
    "QueryBasis",
    "RealEstate",
    "ResponseFormat",
    "Row",
    "Table",
    "Weather",
    "catalog",
    "clean",
    "land_region",
    "latlon_to_grid",
    "lawd_code",
    "temp_region",
]
