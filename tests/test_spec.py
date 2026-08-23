"""clean() -- typed parsing per field kind, and the key-drop rules."""

import pytest

from pydatagokr._spec import Field, Table, _date_ym, _date_ymd, _integer, _ratio, clean
from pydatagokr.services.kofia import CMA_STATUS, DLS_DLB, MARKET_FUNDS, OVERSEAS_DERIVATIVES
from pydatagokr.services.procurement import SERVICES


def test_market_funds_row_parses_every_kind():
    rows = [{
        "basDt":                     "20240105",
        "invrDpsgAmt":               "50,123",
        "onbdDrvPrdTrRcAdvAmt":      "1234.0",       # decimal-formatted integer
        "toCstRpchCndBndSlgBal":     "-",            # vendor missing marker
        "brkTrdUcolMny":             "",
        "brkTrdUcolMnyVsOppsTrdAmt": "77",
        "ucolMnyVsOppsTrdRlImpt":    "8.5",
    }]
    assert clean(rows, MARKET_FUNDS) == [{
        "base_date":                          "2024-01-05",
        "investor_deposit":                50123,
        "derivatives_deposit":             1234,
        "customer_rp_sale_balance":        None,
        "brokerage_receivable":            None,
        "forced_sell_amount":              77,
        "forced_sell_to_receivable_ratio": 8.5,
    }]


def test_fractional_amount_is_none_not_rounded():
    rows = [{"basDt": "20240105", "invrDpsgAmt": "3.8"}]
    cleaned = clean(rows, MARKET_FUNDS)
    assert cleaned[0]["investor_deposit"] is None    # a contract breach, not a round


def test_integer_above_float_precision_stays_exact():
    # 2**53 + 1 is the first integer a float cannot represent. Both the plain form (the int()
    # path) and the decimal-formatted form (which goes through Decimal, not a lossy float)
    # must keep the won amount exact.
    big = 9007199254740993                           # 2**53 + 1
    for raw in (str(big), f"{big}.0"):
        rows = [{"basDt": "20240105", "invrDpsgAmt": raw}]
        assert clean(rows, MARKET_FUNDS)[0]["investor_deposit"] == big


def test_parsers_reject_non_ascii_digits():
    # int() and str.isdigit() accept full-width / Arabic-Indic digits, but a won/count/date is
    # always ASCII -- accepting them would let _date_ym emit a mixed-width "２０２４-０１", so every
    # parser rejects them consistently. The real ASCII forms still parse.
    assert _integer("１２３４") is None and _integer("٠١٢٣") is None
    assert _date_ym("２０２４０１") is None
    assert _date_ymd("２０２４０１０５") is None
    # _ratio/_decimal reject them too, so a full-width value does not type one vendor row two
    # ways (a ratio field parsing "３.８" while the same digits in an int field return None).
    assert _ratio("３.８") is None and _ratio("٣.٨") is None
    assert _integer("1234") == 1234 and _date_ym("2026.01") == "2026-01" and _ratio("3.8") == 3.8


def test_table_rejects_duplicate_columns_and_tokens():
    with pytest.raises(ValueError, match="duplicate clean column"):
        Table("t", "op", (Field("a", "dup", "text"), Field("b", "dup", "text")))
    with pytest.raises(ValueError, match="duplicate vendor token"):
        Table("t", "op", (Field("dup", "a", "text"), Field("dup", "b", "text")))


def test_integer_does_not_expand_a_scientific_exponent_bomb():
    # A malicious huge-exponent value must NOT materialize a billion-digit int (a DoS); it is
    # not a plain integer won/count, so it becomes None -- like float's inf overflow.
    assert _integer("1E999999999") is None
    assert _integer("9.9E1000000") is None
    assert _integer("1234.0") == 1234                # the real decimal-integer case still works


def test_non_finite_numbers_become_none():
    # Vendor "NaN"/"inf"/"Infinity" must not become a real nan/inf (int or ratio) -> None.
    rows = [{"basDt": "20240105", "invrDpsgAmt": "inf",
             "ucolMnyVsOppsTrdRlImpt": "NaN"}]
    cleaned = clean(rows, MARKET_FUNDS)
    assert cleaned[0]["investor_deposit"] is None
    assert cleaned[0]["forced_sell_to_receivable_ratio"] is None


def test_missing_date_drops_the_row():
    assert clean([{"invrDpsgAmt": "1"}], MARKET_FUNDS) == []
    assert clean([{"basDt": "2024-01-05", "invrDpsgAmt": "1"}], MARKET_FUNDS) == []


def test_invalid_calendar_date_drops_the_row():
    assert clean([{"basDt": "20240230"}], MARKET_FUNDS) == []


def test_missing_key_dimension_drops_a_composite_key_row():
    rows = [{"basDt": "20240105", "mngInvTgt": "RP형", "invrCtg": "", "actCnt": "10"}]
    assert clean(rows, CMA_STATUS) == []


def test_wide_key_table_keeps_a_row_with_a_null_dimension():
    rows = [{"basDt": "202401", "byPrdGrp": "", "actCtg": "자기", "trqu": "5"}]
    cleaned = clean(rows, OVERSEAS_DERIVATIVES)
    assert len(cleaned) == 1
    assert cleaned[0]["product_group"] is None       # kept, dimension NULL
    assert cleaned[0]["trade_volume"] == 5


def test_date_ym_parses_and_rejects():
    rows = [{"basDt": "202401", "ctgDlbDls": "합계", "ctgPrplcPsub": "공모",
             "presCtg": "발행실적", "amt": "9", "ccnt": "2"}]
    cleaned = clean(rows, DLS_DLB)
    assert cleaned[0]["base_ym"] == "2024-01"
    assert cleaned[0]["amount_krw"] == 9             # unit encoded in the column name
    dotted = [{**rows[0], "basDt": "2026.01"}]       # customs "YYYY.MM" -> separators stripped
    assert clean(dotted, DLS_DLB)[0]["base_ym"] == "2026-01"
    bad = [{**rows[0], "basDt": "2024"}]             # not a YYYYMM -> row dropped
    assert clean(bad, DLS_DLB) == []


def test_blank_and_marker_text_is_none():
    rows = [{"basDt": "202401", "byPrdGrp": "None", "actCtg": "nan", "xchNm": "CME"}]
    cleaned = clean(rows, OVERSEAS_DERIVATIVES)
    assert cleaned[0]["product_group"] is None
    assert cleaned[0]["account_type"] is None
    assert cleaned[0]["exchange"] == "CME"


def test_table_derived_properties():
    assert MARKET_FUNDS.date_column == "base_date"
    assert MARKET_FUNDS.key_columns == ("base_date",)
    assert MARKET_FUNDS.columns[0] == "base_date"
    assert CMA_STATUS.key_columns == ("base_date", "management_target", "investor_type")
    assert OVERSEAS_DERIVATIVES.is_wide_key


def test_date_column_is_none_for_a_wide_key_table_without_a_date_field():
    # A wide-key table keyed by a surrogate id, not a period, has no date field; the
    # property returns None rather than raising StopIteration.
    assert SERVICES.date_column is None


# One single-field table per kind, so clean() exercises exactly one parser at a time.
def _table(kind):
    return Table("t", "op", (Field("v", "value", kind),))


_YMD     = _table("date_ymd")
_YM      = _table("date_ym")
_INT     = _table("int")
_RATIO   = _table("ratio")
_DECIMAL = _table("decimal")
_TEXT    = _table("text")

_DROP = object()   # sentinel: a required field parsed to None drops the whole row


# (table, raw input, expected cleaned value) -- _DROP means the row is dropped entirely.
# A date field is required (kind starts with "date"), so a None parse drops it; the other
# kinds are not keys here, so a None parse is kept as a None value.
_MATRIX = [
    # date_ymd: 8-digit YYYYMMDD, else the row is dropped
    (_YMD, "20240105", "2024-01-05"),
    (_YMD, None,       _DROP),
    (_YMD, "",         _DROP),
    (_YMD, "-",        _DROP),
    (_YMD, "20241301", _DROP),   # invalid month
    (_YMD, "20240229", "2024-02-29"),  # leap day in a leap year is valid
    (_YMD, "20230229", _DROP),   # Feb 29 in a non-leap year is dropped
    (_YMD, "2024-01-05", _DROP), # separators -> not 8 digits
    (_YMD, "1,234",    _DROP),
    # date_ym: 6 digits after stripping separators, else dropped
    (_YM, "202401", "2024-01"),
    (_YM, "202412", "2024-12"),   # December, the upper valid month boundary
    (_YM, "2026.01", "2026-01"),  # dotted customs form
    (_YM, "202400",  _DROP),      # month 00 is not a valid month
    (_YM, "202413",  _DROP),      # month 13 is not a valid month
    (_YM, None,      _DROP),
    (_YM, "",        _DROP),
    (_YM, "-",       _DROP),
    (_YM, "2024",    _DROP),      # only 4 digits
    (_YM, "1,234",   _DROP),      # only 4 digits after stripping the comma
    # int: exact int; commas stripped; a fractional value is None, not a round
    (_INT, "1234",   1234),
    (_INT, "1,234",  1234),
    (_INT, "1234.0", 1234),       # decimal-formatted integer
    (_INT, "1e3",    1000),       # scientific notation that is integral is accepted
    (_INT, "3.0e2",  300),        # scientific notation, integral value
    (_INT, "3.8e0",  None),       # scientific notation with a fractional value -> None
    (_INT, "3.8",    None),       # a real fraction is not an integer won/count
    (_INT, None,     None),
    (_INT, "",       None),
    (_INT, "-",      None),
    (_INT, "abc",    None),
    # ratio: float; commas stripped
    (_RATIO, "8.5",     8.5),
    (_RATIO, "1,234.5", 1234.5),
    (_RATIO, "1,234",   1234.0),
    (_RATIO, None,      None),
    (_RATIO, "",        None),
    (_RATIO, "-",       None),
    (_RATIO, "abc",     None),
    # decimal: same parsing as ratio, a distinct kind for honest schemas
    (_DECIMAL, "84.5",    84.5),
    (_DECIMAL, "1,234.5", 1234.5),
    (_DECIMAL, None,      None),
    (_DECIMAL, "",        None),
    (_DECIMAL, "-",       None),
    (_DECIMAL, "abc",     None),
    # text: stripped; only ""/"nan"/"None" are missing -- "-" and "1,234" are real text
    (_TEXT, "  hello ", "hello"),
    (_TEXT, "-",        "-"),
    (_TEXT, "1,234",    "1,234"),
    (_TEXT, "nan",      None),
    (_TEXT, "None",     None),
    (_TEXT, None,       None),
    (_TEXT, "",         None),
]


@pytest.mark.parametrize("table,raw,expected", _MATRIX,
                         ids=[f"{table.fields[0].kind}-{raw!r}" for table, raw, _ in _MATRIX])
def test_parser_matrix(table, raw, expected):
    rows = clean([{"v": raw}], table)
    if expected is _DROP:
        assert rows == []
    else:
        [row] = rows
        if isinstance(expected, float):
            assert row["value"] == pytest.approx(expected)   # never == on a parsed float
        else:
            assert row == {"value": expected}
