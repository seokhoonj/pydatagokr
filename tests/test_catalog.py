"""The offline catalog -- registry-derived services, operations, and field schemas."""

import pytest

from pydatagokr import catalog


def test_services_are_registry_derived():
    listed = {entry["service"]: entry for entry in catalog.services()}
    assert set(listed) == {"kofia", "customs", "holidays", "realestate", "weather", "airquality",
                          "midforecast", "procurement"}
    assert listed["kofia"]["base_url"].endswith("GetKofiaStatisticsInfoService")
    assert "관세청" in listed["customs"]["agency"]


def test_operations_lists_a_services_tables():
    ops = catalog.operations("kofia")
    assert "market_funds" in ops and "overseas_derivatives" in ops
    assert catalog.operations("customs") == ["item_trade"]


def test_customs_fields_are_the_confirmed_tokens():
    schema = catalog.fields("customs", "item_trade")
    assert [(field["token"], field["column"]) for field in schema] == [
        ("year",        "period"),
        ("hsCode",      "hs_code"),
        ("statKor",     "item_name"),
        ("expDlr",      "export_usd"),
        ("expWgt",      "export_weight_kg"),
        ("impDlr",      "import_usd"),
        ("impWgt",      "import_weight_kg"),
        ("balPayments", "trade_balance_usd"),
    ]


def test_fields_returns_the_clean_column_schema():
    schema = catalog.fields("kofia", "market_funds")
    assert schema[0] == {"token": "basDt", "column": "base_date",
                         "kind": "date_ymd", "is_key": True, "required": True}
    columns = [field["column"] for field in schema]
    assert "investor_deposit" in columns
    assert all(set(field) == {"token", "column", "kind", "is_key", "required"} for field in schema)


def test_fields_required_reflects_wide_key_not_just_is_key():
    # For a wide-key table clean() does NOT drop on a missing natural-key dimension, so the
    # schema must report required=False there even though is_key=True -- a consumer keying on
    # is_key alone would build a NOT NULL that clean() then violates with a None.
    goods = {field["column"]: field for field in catalog.fields("procurement", "goods")}
    assert goods["notice_no"]["is_key"] is True and goods["notice_no"]["required"] is False
    # A composite-key table still marks its key columns required.
    market = {field["column"]: field for field in catalog.fields("kofia", "fund_net_asset")}
    assert market["fund_type"]["is_key"] is True and market["fund_type"]["required"] is True


def test_unknown_service_raises_value_error():
    with pytest.raises(ValueError, match="unknown service"):
        catalog.operations("nope")
    with pytest.raises(ValueError, match="unknown service"):
        catalog.fields("nope", "market_funds")


def test_unknown_operation_raises_value_error():
    with pytest.raises(ValueError, match="unknown operation"):
        catalog.fields("kofia", "nope")
