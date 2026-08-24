"""RealEstate -- deal_date synthesis, decimal area, the four operations, and the RTMS
three-digit result code, offline."""

import pytest

from pydatagokr.services.realestate import RealEstate


def _xml(items, total):
    rows = "".join(
        "<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in item.items()) + "</item>"
        for item in items)
    # RTMS answers a three-digit result code ("000"), not the two-digit "00".
    return (f"<response><header><resultCode>000</resultCode><resultMsg>OK</resultMsg>"
            f"</header><body><items>{rows}</items>"
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


_TRADE_ROW = {
    "dealYear":   "2024",
    "dealMonth":  "1",
    "dealDay":    "19",
    "sggCd":      "11110",
    "umdNm":      "숭인동",
    "jibun":      "766",
    "aptNm":      "종로청계힐스테이트",
    "excluUseAr": "84.9478",
    "floor":      "13",
    "buildYear":  "2009",
    "dealAmount": "101,300",
    "dealingGbn": "중개거래",
    "aptDong":    "105",
}


def _re(raw):
    realestate = RealEstate(api_key="k")
    opener = _FakeOpener(raw)
    realestate._session._opener = opener
    return realestate, opener


def test_apt_trade_synthesizes_deal_date_and_types_the_measures():
    realestate, _ = _re(_xml([_TRADE_ROW], 1))
    row = realestate.apt_trade(lawd_code="11110", deal_ym="202401")[0]
    assert row["deal_date"] == "2024-01-19"       # from dealYear/dealMonth/dealDay
    assert row["exclusive_area"] == pytest.approx(84.9478)       # decimal -> float
    assert row["deal_amount"] == 101300    # comma stripped -> int
    assert row["floor"] == 13
    assert row["apt_name"] == "종로청계힐스테이트"
    assert "dealYear" not in row                  # split parts collapse into deal_date


def test_a_non_numeric_date_part_drops_only_that_row_not_the_whole_fetch():
    # A malformed vendor date part must not crash the entire month's fetch: _deal_date
    # yields no date, so _spec.clean drops just that one row on its required date-check.
    bad = dict(_TRADE_ROW, dealDay="19일")            # a stray non-numeric day
    realestate, _ = _re(_xml([bad, dict(_TRADE_ROW)], 2))
    rows = realestate.apt_trade(lawd_code="11110", deal_ym="202401")
    assert len(rows) == 1                              # the good row survives; no crash
    assert rows[0]["deal_date"] == "2024-01-19"


def test_raw_passthrough_keeps_the_vendor_tokens_unchanged():
    realestate, _ = _re(_xml([_TRADE_ROW], 1))
    assert realestate.apt_trade(lawd_code="11110", deal_ym="202401", clean=False) == [_TRADE_ROW]


def test_the_operation_path_and_filters_reach_the_vendor():
    realestate, opener = _re(_xml([], 0))
    realestate.apt_rent(lawd_code="11110", deal_ym="202401")
    query = opener.requests[0].full_url
    assert "RTMSDataSvcAptRent/getRTMSDataSvcAptRent" in query   # per-service path segment
    assert "LAWD_CD=11110" in query
    assert "DEAL_YMD=202401" in query


def test_a_three_digit_result_code_is_read_as_success():
    realestate, _ = _re(_xml([_TRADE_ROW], 1))
    assert len(realestate.apt_trade(lawd_code="11110", deal_ym="202401")) == 1


def test_fetch_rejects_an_unknown_operation():
    realestate, _ = _re(_xml([], 0))
    with pytest.raises(ValueError, match="unknown operation"):
        realestate.fetch("nope", lawd_code="11110", deal_ym="202401")


# Fields shared by the three sale-type operations (매매·매매상세·분양권). deal_date is
# synthesized from dealYear/dealMonth/dealDay before cleaning.
_SALE_RAW_CORE = {
    "dealYear":   "2024",
    "dealMonth":  "1",
    "dealDay":    "19",
    "sggCd":      "11110",
    "umdNm":      "숭인동",
    "jibun":      "766",
    "aptNm":      "종로청계힐스테이트",
    "excluUseAr": "84.5",
    "floor":      "13",
    "buildYear":  "2009",
    "dealAmount": "101,300",
    "dealingGbn": "중개거래",
    "buyerGbn":   "개인",
    "slerGbn":    "법인",
    "cdealType":  "",
    "cdealDay":   "",
    "estateAgentSggNm": "서울 종로구",
}
_SALE_CLEAN_CORE = {
    "deal_date":      "2024-01-19",
    "lawd_code":    "11110",
    "dong":           "숭인동",
    "jibun":          "766",
    "apt_name":       "종로청계힐스테이트",
    "exclusive_area": 84.5,
    "floor":          13,
    "build_year":     2009,
    "deal_amount": 101300,
    "dealing_type":   "중개거래",
    "buyer_type":     "개인",
    "seller_type":    "법인",
    "cancel_type":    None,
    "cancel_date":    None,
    "agent_region":   "서울 종로구",
}

# (operation name, raw row, exact cleaned row, vendor operation path) -- one case per
# operation, each carrying its own distinct fields on top of the shared core.
_CASES = [
    (
        "apt_trade",
        {**_SALE_RAW_CORE, "aptDong": "105", "landLeaseholdGbn": "N", "rgstDate": "24.01.25"},
        {**_SALE_CLEAN_CORE, "apt_dong": "105", "land_leasehold": "N",
         "register_date": "24.01.25"},
        "RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    ),
    (
        "apt_trade_detail",
        {**_SALE_RAW_CORE, "aptDong": "105", "aptSeq": "11110-100", "bonbun": "0766",
         "bubun": "0000", "landCd": "1", "landLeaseholdGbn": "N", "umdCd": "12300",
         "rgstDate": "24.01.25", "roadNm": "종로", "roadNmCd": "400", "roadNmBonbun": "12",
         "roadNmBubun": "0", "roadNmSeq": "01", "roadNmSggCd": "11110", "roadNmbCd": "0"},
        {**_SALE_CLEAN_CORE, "apt_dong": "105", "apt_seq": "11110-100", "main_no": "0766",
         "sub_no": "0000", "land_code": "1", "land_leasehold": "N", "dong_code": "12300",
         "register_date": "24.01.25", "road_name": "종로", "road_code": "400",
         "road_main_no": "12", "road_sub_no": "0", "road_seq": "01",
         "road_sgg_code": "11110", "road_basement_yn": "0"},
        "RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    ),
    (
        "apt_presale",
        {**_SALE_RAW_CORE, "ownershipGbn": "분양권", "sggNm": "종로구"},
        {**_SALE_CLEAN_CORE, "ownership_type": "분양권", "sgg_name": "종로구"},
        "RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade",
    ),
    (
        "apt_rent",
        {"dealYear": "2024", "dealMonth": "1", "dealDay": "19", "sggCd": "11110",
         "umdNm": "숭인동", "jibun": "766", "aptNm": "종로청계힐스테이트", "excluUseAr": "84.5",
         "floor": "13", "buildYear": "2009", "deposit": "50,000", "monthlyRent": "0",
         "contractType": "신규", "contractTerm": "202401~202601", "preDeposit": "0",
         "preMonthlyRent": "0", "useRRRight": "", "aptSeq": "11110-100", "roadnm": "종로",
         "roadnmcd": "400", "roadnmbonbun": "12", "roadnmbubun": "0", "roadnmseq": "01",
         "roadnmsggcd": "11110", "roadnmbcd": "0"},
        {"deal_date": "2024-01-19", "lawd_code": "11110", "dong": "숭인동", "jibun": "766",
         "apt_name": "종로청계힐스테이트", "exclusive_area": 84.5, "floor": 13,
         "build_year": 2009, "deposit": 50000, "monthly_rent": 0,
         "contract_type": "신규", "contract_term": "202401~202601",
         "prev_deposit": 0, "prev_monthly_rent": 0,
         "renewal_right_used": None, "apt_seq": "11110-100", "road_name": "종로",
         "road_code": "400", "road_main_no": "12", "road_sub_no": "0", "road_seq": "01",
         "road_sgg_code": "11110", "road_basement_yn": "0"},
        "RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
    ),
]


@pytest.mark.parametrize("name,raw_row,clean_row,operation", _CASES,
                         ids=[case[0] for case in _CASES])
def test_every_operation_types_its_row_and_wires_the_filters(
        name, raw_row, clean_row, operation):
    realestate, opener = _re(_xml([raw_row], 1))
    rows = realestate.fetch(name, lawd_code="11110", deal_ym="202401")
    assert rows == [clean_row]                        # exact typed row, all columns
    query = opener.requests[0].full_url
    assert operation in query                         # the operation's own service segment
    assert "LAWD_CD=11110" in query
    assert "DEAL_YMD=202401" in query
