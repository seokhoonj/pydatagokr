"""Every typed per-operation wrapper forwards the right operation to ``fetch``.

The wrappers were collapsed to a single ``return self.fetch(name, ..., clean=clean)`` line, so a
regression could silently forward a wrong operation string or drop a keyword and no existing test
would notice (the ``fetch`` matrix tests exercise ``fetch`` directly, not the wrappers). Each case
here spies on the service's ``fetch`` and pins the exact operation name and keywords the wrapper
must pass, for both the default ``clean`` and ``clean=False``.
"""

import pytest

from pydatagokr.services.holidays import Holidays
from pydatagokr.services.kofia import KOFIA
from pydatagokr.services.midforecast import MidForecast
from pydatagokr.services.procurement import Procurement
from pydatagokr.services.realestate import RealEstate
from pydatagokr.services.weather import Weather

# (service class, wrapper method, call kwargs, expected operation, expected forwarded kwargs).
# The forwarded kwargs are what the wrapper adds on top of clean -- including the defaults it
# fills in for an argument the caller omitted (weather's base_date/base_time, procurement's
# query_basis, holidays' month).
_CASES = [
    (KOFIA, "market_funds", {"begin": "20240101", "end": "20240131"},
     "market_funds", {"begin": "20240101", "end": "20240131"}),
    (KOFIA, "credit_balance", {"begin": "20240101", "end": "20240131"},
     "credit_balance", {"begin": "20240101", "end": "20240131"}),
    (RealEstate, "apt_trade", {"lawd_code": "11110", "deal_ym": "202401"},
     "apt_trade", {"lawd_code": "11110", "deal_ym": "202401"}),
    (RealEstate, "apt_trade_detail", {"lawd_code": "11110", "deal_ym": "202401"},
     "apt_trade_detail", {"lawd_code": "11110", "deal_ym": "202401"}),
    (RealEstate, "apt_rent", {"lawd_code": "11110", "deal_ym": "202401"},
     "apt_rent", {"lawd_code": "11110", "deal_ym": "202401"}),
    (RealEstate, "apt_presale", {"lawd_code": "11110", "deal_ym": "202401"},
     "apt_presale", {"lawd_code": "11110", "deal_ym": "202401"}),
    (Weather, "forecast", {"nx": 60, "ny": 127},
     "forecast", {"base_date": None, "base_time": None, "nx": 60, "ny": 127}),
    (Weather, "ultra_forecast", {"nx": 60, "ny": 127},
     "ultra_forecast", {"base_date": None, "base_time": None, "nx": 60, "ny": 127}),
    (Weather, "nowcast", {"nx": 60, "ny": 127},
     "nowcast", {"base_date": None, "base_time": None, "nx": 60, "ny": 127}),
    (MidForecast, "land", {"regid": "11B00000", "base_time": "202608111800"},
     "land", {"regid": "11B00000", "base_time": "202608111800"}),
    (MidForecast, "temperature", {"regid": "11B10101", "base_time": "202608111800"},
     "temperature", {"regid": "11B10101", "base_time": "202608111800"}),
    (Procurement, "goods", {"begin": "202608010000", "end": "202608102359"},
     "goods", {"begin": "202608010000", "end": "202608102359", "query_basis": "1"}),
    (Procurement, "services", {"begin": "202608010000", "end": "202608102359"},
     "services", {"begin": "202608010000", "end": "202608102359", "query_basis": "1"}),
    (Procurement, "construction", {"begin": "202608010000", "end": "202608102359"},
     "construction", {"begin": "202608010000", "end": "202608102359", "query_basis": "1"}),
    (Procurement, "foreign", {"begin": "202608010000", "end": "202608102359"},
     "foreign", {"begin": "202608010000", "end": "202608102359", "query_basis": "1"}),
    (Holidays, "holidays", {"year": 2026},
     "holidays", {"year": 2026, "month": None}),
]


@pytest.mark.parametrize("service_cls,wrapper,call_kwargs,operation,forwarded", _CASES,
                         ids=[f"{cls.__name__}.{name}" for cls, name, *_ in _CASES])
def test_wrapper_forwards_operation_and_kwargs(
        service_cls, wrapper, call_kwargs, operation, forwarded, monkeypatch):
    monkeypatch.setenv("DATAGOKR_API_KEY", "test-key")   # construction only; fetch is replaced
    captured: dict[str, object] = {}

    def spy(self, name, **kwargs):
        captured["name"] = name
        captured["kwargs"] = kwargs
        return []

    monkeypatch.setattr(service_cls, "fetch", spy)
    surface = service_cls()

    getattr(surface, wrapper)(**call_kwargs)                       # clean defaults to True
    assert captured["name"] == operation
    assert captured["kwargs"] == {**forwarded, "clean": True}

    getattr(surface, wrapper)(**call_kwargs, clean=False)          # raw path
    assert captured["name"] == operation
    assert captured["kwargs"] == {**forwarded, "clean": False}
