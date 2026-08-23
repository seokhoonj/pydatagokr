"""KOFIA -- every operation's typed row, its vendor path, and the right date-bound param
(daily basDt / monthly basYm, each bound normalised to the field width and the end pushed
one sort step up so the caller's end is inclusive), over the JSON session, offline."""

import json
import urllib.parse

import pytest

from pydatagokr.services.kofia import KOFIA


def _json(items, total):
    body = {"response": {"header": {"resultCode": "00", "resultMsg": "OK"},
                         "body": {"items": {"item": items}, "totalCount": total}}}
    return json.dumps(body).encode()


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


def _kofia(raw):
    kofia = KOFIA(api_key="k")
    opener = _FakeOpener(raw)
    kofia._session._opener = opener
    return kofia, opener


# (operation name, one representative raw row, its exact cleaned row, the vendor operation
# path, the begin/end bound params) -- daily tables filter on basDt at width 8, monthly ones
# on their date token at width 6 (basYm for 신탁규모, basDt else); the end bound (called with
# end="20240315") carries the trailing '9' that makes the vendor's exclusive upper inclusive.
_CASES = [
    (
        "market_funds",
        {"basDt": "20240131", "invrDpsgAmt": "50,123", "onbdDrvPrdTrRcAdvAmt": "1,000",
         "toCstRpchCndBndSlgBal": "200", "brkTrdUcolMny": "30",
         "brkTrdUcolMnyVsOppsTrdAmt": "77", "ucolMnyVsOppsTrdRlImpt": "8.5"},
        {"base_date": "2024-01-31", "investor_deposit": 50123, "derivatives_deposit": 1000,
         "customer_rp_sale_balance": 200, "brokerage_receivable": 30,
         "forced_sell_amount": 77, "forced_sell_to_receivable_ratio": 8.5},
        "getSecuritiesMarketTotalCapitalInfo",
        "beginBasDt=20240131", "endBasDt=202403159",
    ),
    (
        "credit_balance",
        {"basDt": "20240131", "crdTrFingWhl": "1,000", "crdTrFingScrs": "600",
         "crdTrFingKosdaq": "400", "crdTrLndrWhl": "50", "crdTrLndrScrs": "30",
         "crdTrLndrKosdaq": "20", "sbscCapLn": "5", "dpsgScrtMogFing": "90"},
        {"base_date": "2024-01-31", "margin_loan_total": 1000, "margin_loan_kospi": 600,
         "margin_loan_kosdaq": 400, "stock_loan_total": 50, "stock_loan_kospi": 30,
         "stock_loan_kosdaq": 20, "subscription_loan": 5, "collateral_loan": 90},
        "getGrantingOfCreditBalanceInfo",
        "beginBasDt=20240131", "endBasDt=202403159",
    ),
    (
        "fund_net_asset",
        {"basDt": "20240131", "ctg": "PEF", "tstMthdCtg": "공모", "nPptTotAmt": "9,999"},
        {"base_date": "2024-01-31", "fund_type": "PEF", "offering_type": "공모",
         "net_asset_total": 9999},
        "getFundTotalNetEssetInfo",
        "beginBasDt=20240131", "endBasDt=202403159",
    ),
    (
        "cma_status",
        {"basDt": "20240131", "mngInvTgt": "RP형", "invrCtg": "개인", "scrtCmpyCnt": "10",
         "actCnt": "1,234", "actBal": "5,000"},
        {"base_date": "2024-01-31", "management_target": "RP형", "investor_type": "개인",
         "securities_firm_count": 10, "account_count": 1234, "account_balance": 5000},
        "getCMAStatus",
        "beginBasDt=20240131", "endBasDt=202403159",
    ),
    (
        "trust_scale",
        {"basYm": "202401", "bzds": "증권", "tstCtg": "금전신탁", "kind": "특정금전",
         "iqBs": "수탁총액", "val": "12,345"},
        {"base_ym": "2024-01", "sector": "증권", "trust_type": "금전신탁",
         "trust_kind": "특정금전", "measure_basis": "수탁총액", "measure_value": 12345},
        "getTrustScaleInfo",
        "beginBasYm=202401", "endBasYm=2024039",
    ),
    (
        "dls_dlb",
        {"basDt": "202401", "ctgDlbDls": "합계", "ctgPrplcPsub": "공모",
         "presCtg": "발행실적", "amt": "9,000", "ccnt": "12"},
        {"base_ym": "2024-01", "product_type": "합계", "offering_type": "공모",
         "status_type": "발행실적", "amount_krw": 9000, "deal_count": 12},
        "getDLSAndDLBInfo",
        "beginBasDt=202401", "endBasDt=2024039",
    ),
    (
        "els_elb",
        {"basDt": "202401", "ctgElbEls": "ELS", "ctgPrplcPsub": "공모",
         "presCtg": "발행실적", "amt": "8,000", "ccnt": "7"},
        {"base_ym": "2024-01", "product_type": "ELS", "offering_type": "공모",
         "status_type": "발행실적", "amount_krw": 8000, "deal_count": 7},
        "getELSAndELBInfo",
        "beginBasDt=202401", "endBasDt=2024039",
    ),
    (
        "overseas_derivatives",
        {"basDt": "202401", "byPrdGrp": "통화", "actCtg": "자기", "ctgBsonCntrForm": "콜옵션",
         "prdNm": "EUR/USD", "brkPn": "개인", "xchNm": "CME", "csfBsonCntrForm": "옵션",
         "byNtnl": "미국", "prdGrp": "통화선물", "trqu": "5", "trPrcUsd": "1,000"},
        {"base_ym": "2024-01", "product_group": "통화", "account_type": "자기",
         "contract_form": "콜옵션", "product_name": "EUR/USD", "customer_type": "개인",
         "exchange": "CME", "contract_class": "옵션", "country": "미국",
         "underlying_asset_group": "통화선물", "trade_volume": 5, "trade_value_usd": 1000},
        "getDerivationProductTradingInfo",
        "beginBasDt=202401", "endBasDt=2024039",
    ),
]


@pytest.mark.parametrize("name,raw_row,clean_row,operation,begin_param,end_param", _CASES,
                         ids=[case[0] for case in _CASES])
def test_every_operation_types_its_row_and_wires_the_bounds(
        name, raw_row, clean_row, operation, begin_param, end_param):
    kofia, opener = _kofia(_json([raw_row], 1))
    rows = kofia.fetch(name, begin="20240131", end="20240315")
    assert rows == [clean_row]                       # exact typed row, all columns
    url = opener.requests[0].full_url
    assert operation in url                           # the operation's own vendor path
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    for expected in (begin_param, end_param):         # exact value: a dropped YYYYMM
        key, value = expected.split("=")              # truncation ("...202401" vs "20240131")
        assert params[key] == [value]                 # would fail here, not pass on substring


def _params(opener):
    url = opener.requests[0].full_url
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)


# The vendor filters basDt as a fixed-width STRING with an EXCLUSIVE upper bound
# (basDt < end...), verified live for every operation, daily and monthly alike. So the
# emitted end bound must sort strictly AFTER the caller's last wanted unit, or that unit
# (and, for begin==end, the whole result) is silently dropped.
@pytest.mark.parametrize("name,base,lo,hi", [
    ("market_funds", "BasDt", "20240102", "202403159"),   # daily: width 8, end + '9'
    ("credit_balance", "BasDt", "20240102", "202403159"),
    ("dls_dlb", "BasDt", "202401", "2024039"),            # monthly basDt: width 6, end + '9'
    ("els_elb", "BasDt", "202401", "2024039"),
    ("overseas_derivatives", "BasDt", "202401", "2024039"),
    ("trust_scale", "BasYm", "202401", "2024039"),        # monthly basYm
])
def test_end_bound_sorts_after_its_unit_so_the_last_unit_is_included(name, base, lo, hi):
    kofia, opener = _kofia(_json([], 0))
    kofia.fetch(name, begin="20240102", end="20240315")
    params = _params(opener)
    assert params[f"begin{base}"] == [lo]             # lower bound is inclusive as-is
    assert params[f"end{base}"] == [hi]               # upper bound pushed one sort step up


@pytest.mark.parametrize("name,base,point", [
    ("market_funds", "BasDt", "20240102"),            # daily single day
    ("dls_dlb", "BasDt", "202401"),                   # monthly single month
    ("trust_scale", "BasYm", "202401"),
])
def test_single_point_query_spans_a_nonempty_range(name, base, point):
    kofia, opener = _kofia(_json([], 0))
    kofia.fetch(name, begin=point, end=point)         # begin == end must not be empty [x, x)
    params = _params(opener)
    lo, hi = params[f"begin{base}"][0], params[f"end{base}"][0]
    assert lo <= point < hi                           # the point falls inside [lo, hi)
