"""MidForecast -- XML session, wide day-columns, int/text typing, two ops, offline."""

import pytest

from pydatagokr.services.midforecast import MidForecast


def _xml(items, total):
    rows = "".join(
        "<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in item.items()) + "</item>"
        for item in items)
    return (f"<response><header><resultCode>00</resultCode>"
            f"<resultMsg>NORMAL_SERVICE</resultMsg></header>"
            f"<body><items>{rows}</items>"
            f"<totalCount>{total}</totalCount></body></response>").encode()


class _FakeResponse:
    def __init__(self, raw):
        self._raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._raw


class _FakeOpener:
    def __init__(self, raw):
        self._raw = raw
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        return _FakeResponse(self._raw)


# A 1800 announcement: day 4 is absent (its columns empty), days 5-10 present.
_LAND_ROW = {
    "regId": "11B00000",
    "rnSt4Am": "", "rnSt4Pm": "",
    "rnSt5Am": "20", "rnSt5Pm": "30", "rnSt6Am": "40", "rnSt6Pm": "40",
    "rnSt7Am": "60", "rnSt7Pm": "60", "rnSt8": "10", "rnSt9": "10", "rnSt10": "20",
    "wf5Am": "구름많음", "wf5Pm": "흐림", "wf8": "맑음", "wf10": "비",
}

_TA_ROW = {
    "regId": "11B10101",
    "taMin5": "26", "taMax5": "34", "taMin6": "25", "taMax6": "33",
    "taMin10": "24", "taMax10": "31",
}


def _mid(raw):
    mid = MidForecast(api_key="k")
    opener = _FakeOpener(raw)
    mid._session._opener = opener
    return mid, opener


def test_land_types_precip_int_and_sky_text():
    mid, _ = _mid(_xml([_LAND_ROW], 1))
    row = mid.land(regid="11B00000", base_time="202608111800")[0]
    assert row["regid"] == "11B00000"
    assert row["precip_prob_5am"] == 20 and row["precip_prob_7pm"] == 60   # int
    assert row["sky_5am"] == "구름많음" and row["sky_8"] == "맑음"          # text
    assert row["precip_prob_4am"] is None                                  # absent -> None


def test_temperature_types_min_and_max():
    mid, _ = _mid(_xml([_TA_ROW], 1))
    row = mid.temperature(regid="11B10101", base_time="202608111800")[0]
    assert row["temp_min_5"] == 26 and row["temp_max_5"] == 34
    assert row["temp_min_10"] == 24 and row["temp_max_10"] == 31


def test_land_raw_passthrough_keeps_vendor_tokens():
    mid, _ = _mid(_xml([_LAND_ROW], 1))
    assert mid.land(regid="11B00000", base_time="202608111800", clean=False) == [_LAND_ROW]


def test_0600_announcement_keeps_day_four_that_1800_omits():
    # A 0600 announcement carries day 4 (rnSt4Am/wf4Am); a 1800 one does not. The same
    # code must surface the 0600 value AND leave the 1800 day-4 column None -- so a
    # regression that dropped a present day-4 value could not hide behind the 1800 case.
    row_0600 = {"regId": "11B00000", "rnSt4Am": "10", "rnSt4Pm": "20", "wf4Am": "맑음"}
    mid, _ = _mid(_xml([row_0600], 1))
    got_0600 = mid.land(regid="11B00000", base_time="202608110600")[0]
    assert got_0600["precip_prob_4am"] == 10 and got_0600["precip_prob_4pm"] == 20
    assert got_0600["sky_4am"] == "맑음"

    mid, _ = _mid(_xml([_LAND_ROW], 1))                 # the 1800 row omits day 4
    got_1800 = mid.land(regid="11B00000", base_time="202608111800")[0]
    assert got_1800["precip_prob_4am"] is None and got_1800["sky_4am"] is None


def test_operation_path_and_params_reach_the_vendor():
    mid, opener = _mid(_xml([], 0))
    mid.land(regid="11B00000", base_time="202608111800")
    query = opener.requests[0].full_url
    assert "getMidLandFcst" in query
    assert "regId=11B00000" in query
    assert "tmFc=202608111800" in query
    assert "dataType=XML" in query


def test_temperature_operation_path_and_params_reach_the_vendor():
    mid, opener = _mid(_xml([], 0))
    mid.temperature(regid="11B10101", base_time="202608111800")
    query = opener.requests[0].full_url
    assert "getMidTa" in query
    assert "regId=11B10101" in query
    assert "tmFc=202608111800" in query
    assert "dataType=XML" in query


def test_land_with_no_rows_returns_empty_list():
    mid, _ = _mid(_xml([], 0))
    assert mid.land(regid="11B00000", base_time="202608111800") == []


def test_fetch_rejects_an_unknown_operation():
    mid, _ = _mid(_xml([], 0))
    with pytest.raises(ValueError, match="unknown operation"):
        mid.fetch("sea", regid="11B00000", base_time="202608111800")
