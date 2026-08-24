"""Customs -- the XML session, clean-by-default rows, and the raw passthrough, offline."""

from pydatagokr.services.customs import ITEM_TRADE, Customs


def _xml(items, total):
    rows = "".join(
        "<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in item.items()) + "</item>"
        for item in items)
    return (f"<response><header><resultCode>00</resultCode>"
            f"<resultMsg>NORMAL SERVICE.</resultMsg></header>"
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


_ROW = {
    "year":        "2026.01",
    "hsCode":      "8542311000",
    "statKor":     "모노리식(monolithic) 집적회로",
    "expDlr":      "1000",
    "expWgt":      "20",
    "impDlr":      "300",
    "impWgt":      "6",
    "balPayments": "700",
}


def _customs(raw):
    customs = Customs(api_key="k")
    opener = _FakeOpener(raw)
    customs._session._opener = opener
    return customs, opener


def test_item_trade_cleans_by_default():
    customs, opener = _customs(_xml([_ROW], 1))
    rows = customs.item_trade("8542311000", start="202601", end="202601")
    assert rows == [{
        "period":            "2026-01",
        "hs_code":           "8542311000",
        "item_name":         "모노리식(monolithic) 집적회로",
        "export_dollar": 1000,
        "export_weight":   20,
        "import_dollar":  300,
        "import_weight":    6,
        "trade_balance":  700,
    }]
    url = opener.requests[0].full_url
    assert "hsSgn=8542311000" in url
    assert "strtYymm=202601" in url and "endYymm=202601" in url
    assert "_type=json" not in url and "resultType=json" not in url


def test_item_trade_raw_returns_vendor_tokens():
    customs, _ = _customs(_xml([_ROW], 1))
    rows = customs.item_trade("8542311000", start="202601", end="202601", clean=False)
    assert rows == [_ROW]


def test_negative_trade_balance_parses():
    customs, _ = _customs(_xml([{**_ROW, "balPayments": "-1234"}], 1))
    cleaned = customs.item_trade("8542311000", start="202601", end="202601")
    assert cleaned[0]["trade_balance"] == -1234


def test_item_trade_natural_key_includes_the_period():
    # The series is monthly over one HS code, so the period is part of the natural key --
    # a store upserting on key_columns keeps each month rather than collapsing them all
    # onto the HS code alone.
    assert ITEM_TRADE.key_columns == ("period", "hs_code")
