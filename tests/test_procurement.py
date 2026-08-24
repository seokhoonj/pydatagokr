"""Procurement -- XML session, won-int prices, four 업무구분, offline."""

import pytest

from pydatagokr.services.procurement import Procurement


def _xml(items, total):
    rows = "".join(
        "<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in item.items()) + "</item>"
        for item in items)
    return (f"<response><header><resultCode>00</resultCode>"
            f"<resultMsg>정상</resultMsg></header>"
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


_BID_ROW = {
    "bidNtceNo": "R26BK0166146", "bidNtceOrd": "000",
    "bidNtceNm": "2026년 이웃종교스테이 기획 및 행사운영 용역",
    "ntceKindNm": "재공고", "ntceInsttNm": "한국종교인평화회의",
    "dminsttNm": "한국종교인평화회의", "bidMethdNm": "전자입찰",
    "cntrctCnclsMthdNm": "일반경쟁",
    "bidNtceDt": "2026-08-01 10:18:26", "bidClseDt": "2026-08-12 12:00:00",
    "opengDt": "2026-08-12 13:00:00",
    "presmptPrce": "265090909", "asignBdgtAmt": "291600000",
    "ntceInsttOfclNm": "홍길동", "bidNtceDtlUrl": "https://www.g2b.go.kr/x",
    "rgstDt": "2026-08-01 10:18:26",
}


def _proc(raw):
    proc = Procurement(api_key="k")
    opener = _FakeOpener(raw)
    proc._session._opener = opener
    return proc, opener


def test_services_types_the_header():
    proc, _ = _proc(_xml([_BID_ROW], 1))
    row = proc.services(begin="202608010000", end="202608102359")[0]
    assert row["notice_no"] == "R26BK0166146"
    assert row["notice_name"].startswith("2026년")
    assert row["estimated_price"] == 265090909 and row["budget_amount"] == 291600000  # won
    assert row["bid_close_at"] == "2026-08-12 12:00:00"                                # text


def test_construction_without_budget_leaves_it_none():
    row = dict(_BID_ROW)
    del row["asignBdgtAmt"]                       # 공사 announcements omit 배정예산
    proc, _ = _proc(_xml([row], 1))
    got = proc.construction(begin="202608010000", end="202608012359")[0]
    assert got["estimated_price"] == 265090909
    assert got["budget_amount"] is None


def test_services_raw_passthrough_keeps_vendor_tokens():
    proc, _ = _proc(_xml([_BID_ROW], 1))
    assert proc.services(begin="202608010000", end="202608102359",
                         clean=False) == [_BID_ROW]


def test_each_kind_hits_its_own_operation_with_the_window():
    for kind, operation in (("goods", "getBidPblancListInfoThngPPSSrch"),
                            ("services", "getBidPblancListInfoServcPPSSrch"),
                            ("construction", "getBidPblancListInfoCnstwkPPSSrch"),
                            ("foreign", "getBidPblancListInfoFrgcptPPSSrch")):
        proc, opener = _proc(_xml([], 0))
        getattr(proc, kind)(begin="202608010000", end="202608102359")
        query = opener.requests[0].full_url
        assert operation in query
        assert "inqryBgnDt=202608010000" in query
        assert "inqryEndDt=202608102359" in query
        assert "inqryDiv=1" in query
        assert "type=xml" in query


def test_services_with_no_rows_returns_empty_list():
    proc, _ = _proc(_xml([], 0))
    assert proc.services(begin="202608010000", end="202608102359") == []


def test_fetch_rejects_an_unknown_operation():
    proc, _ = _proc(_xml([], 0))
    with pytest.raises(ValueError, match="unknown operation"):
        proc.fetch("lease", begin="202608010000", end="202608102359")
