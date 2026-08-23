"""CLI -- the offline list command, argument validation, and the fetch dispatch paths
with the session's opener faked so no key file or network is needed."""

import json
import os
import subprocess
import sys

import pytest

from pydatagokr import session as session_mod
from pydatagokr.cli import _cell, main


def _body(payload) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _envelope(items, total):
    return _body({"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL"},
                               "body": {"items": {"item": items}, "totalCount": total}}})


def _xml_envelope(items, total):
    rows = "".join(
        "<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in item.items()) + "</item>"
        for item in items)
    return (f"<response><header><resultCode>00</resultCode>"
            f"<resultMsg>NORMAL</resultMsg></header>"
            f"<body><items>{rows}</items>"
            f"<totalCount>{total}</totalCount></body></response>").encode()


def _fake_opener(monkeypatch, body: bytes):
    """Point the package opener at a fake; returns the list of captured URLs."""
    urls = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return body

    def open(request, timeout=None):
        urls.append(request.full_url)
        return _Response()

    monkeypatch.setattr(session_mod._OPENER, "open", open)
    return urls


@pytest.fixture
def keyed_env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("DATAGOKR_API_KEY", "test-key")


# --- list (offline, keyless) -------------------------------------------------

def test_list_needs_no_key(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DATAGOKR_API_KEY", raising=False)
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "kofia market_funds" in out
    assert "kofia credit_balance" in out
    assert "customs item_trade" in out


def test_list_json(capsys):
    assert main(["list", "--json"]) == 0
    operations_by_service = json.loads(capsys.readouterr().out)
    assert set(operations_by_service) == {"kofia", "customs", "holidays", "realestate", "weather",
                                          "airquality", "midforecast", "procurement"}
    assert "market_funds" in operations_by_service["kofia"]
    assert operations_by_service["customs"] == ["item_trade"]


# --- fields (offline, keyless) -----------------------------------------------

def test_fields_needs_no_key(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DATAGOKR_API_KEY", raising=False)
    assert main(["fields", "kofia", "market_funds"]) == 0
    out = capsys.readouterr().out
    assert "basDt" in out and "base_date" in out and "date_ymd" in out


def test_fields_json(capsys):
    assert main(["fields", "kofia", "market_funds", "--json"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema[0] == {"token": "basDt", "column": "base_date",
                         "kind": "date_ymd", "is_key": True, "required": True}


def test_fields_unknown_operation_is_usage_error(capsys):
    assert main(["fields", "kofia", "nope"]) == 2
    assert "unknown operation" in capsys.readouterr().err


def test_fields_unknown_service_is_usage_error(capsys):
    assert main(["fields", "nope", "market_funds"]) == 2
    assert "unknown service" in capsys.readouterr().err


def test_version_flag():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_bad_command_is_usage_error():
    with pytest.raises(SystemExit) as exc:
        main(["frobnicate"])
    assert exc.value.code == 2


def test_prints_korean_on_a_non_utf8_stdout():
    # A Windows cp949 console / an ascii-encoded pipe must not crash when the CLI prints
    # Korean agency names -- main() forces stdout to UTF-8. Run it as a real subprocess with
    # an ascii IO encoding, the way the crash actually reproduces.
    result = subprocess.run(
        [sys.executable, "-m", "pydatagokr", "list"],
        capture_output=True, env={**os.environ, "PYTHONIOENCODING": "ascii"})
    assert result.returncode == 0
    assert "기상청".encode() in result.stdout        # Korean survived as UTF-8, no crash


def test_cell_collapses_control_chars_and_normalizes_nfc():
    import unicodedata
    assert _cell("a\nb\tc\rd") == "a b c d"          # newlines/tabs never break the table
    assert _cell(unicodedata.normalize("NFD", "서울")) == "서울"   # composed for true width
    assert _cell(None) == ""


def test_display_width_counts_hangul_as_two_cells():
    from pydatagokr.cli import _display_width, _pad
    assert _display_width("서울") == 4 and _display_width("ab") == 2   # not len(); Hangul is wide
    assert _pad("서울", 5) == "서울 "                                   # aligned to 5 cells


def test_render_rows_unions_columns_absent_from_the_first_row():
    from pydatagokr.cli import _render_rows
    # A heterogeneous raw (clean=False) response: the 2nd row carries a column the 1st lacks.
    # The text header must union the keys, not key on row 0 alone and silently drop the column.
    table = _render_rows([{"a": "1"}, {"a": "2", "b": "extra"}])
    assert "b" in table.splitlines()[0]              # the extra column is in the header
    assert "extra" in table


def _raise_broken_pipe(args):
    raise BrokenPipeError


def test_handles_a_broken_downstream_pipe(monkeypatch):
    # `datagokr ... | head` closes the pipe early; main() must swallow the BrokenPipeError and
    # exit 1 rather than dump a traceback. (os.dup2/open are stubbed so the handler does not
    # redirect the test runner's own stdout.)
    monkeypatch.setattr("pydatagokr.cli._run_list", _raise_broken_pipe)
    monkeypatch.setattr(os, "dup2", lambda *a: None)   # don't redirect the test runner's stdout
    monkeypatch.setattr(os, "open", lambda *a, **k: 0)
    assert main(["list"]) == 1


# --- kofia -------------------------------------------------------------------

def test_kofia_unknown_operation_is_usage_error(capsys, keyed_env):
    assert main(["kofia", "nope"]) == 2
    assert "unknown operation" in capsys.readouterr().err


def test_kofia_fetch_renders_clean_rows(capsys, keyed_env, monkeypatch):
    urls = _fake_opener(monkeypatch, _envelope(
        [{"basDt": "20240105", "invrDpsgAmt": "50,123"}], total=1))
    assert main(["kofia", "market_funds", "--begin", "20240105", "--end", "20240105"]) == 0
    out = capsys.readouterr().out
    assert "base_date" in out and "2024-01-05" in out           # cleaned columns
    assert "50123" in out
    assert "beginBasDt=20240105" in urls[0]
    assert "resultType=json" in urls[0]


def test_kofia_fetch_json(capsys, keyed_env, monkeypatch):
    _fake_opener(monkeypatch, _envelope([{"basDt": "20240105"}], total=1))
    assert main(["kofia", "market_funds", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["base_date"] == "2024-01-05"


def test_kofia_monthly_operation_uses_year_month_bounds(capsys, keyed_env, monkeypatch):
    # A monthly (basYm) operation maps the bounds to beginBasYm/endBasYm, truncated to
    # YYYYMM -- not the daily beginBasDt that market_funds uses.
    urls = _fake_opener(monkeypatch, _envelope([{"basYm": "202401"}], total=1))
    assert main(["kofia", "trust_scale", "--begin", "20240131", "--end", "20240315"]) == 0
    assert "beginBasYm=202401" in urls[0] and "endBasYm=202403" in urls[0]
    assert "beginBasDt" not in urls[0]


# --- weather ------------------------------------------------------------------

def test_weather_omitted_base_uses_the_latest_announcement(keyed_env, monkeypatch):
    # `datagokr weather forecast --nx --ny` (no --base-date/--base-time) resolves the latest
    # published announcement and sends it to the vendor.
    import pydatagokr.services.weather as weather_mod
    monkeypatch.setattr(weather_mod, "_latest_base", lambda name: ("20260101", "0500"))
    urls = _fake_opener(monkeypatch, _xml_envelope(
        [{"baseDate": "20260101", "baseTime": "0500", "category": "TMP",
          "fcstDate": "20260101", "fcstTime": "0600", "fcstValue": "1",
          "nx": "60", "ny": "127"}], total=1))
    assert main(["weather", "forecast", "--nx", "60", "--ny", "127"]) == 0
    assert "base_date=20260101" in urls[0] and "base_time=0500" in urls[0]


# --- customs -----------------------------------------------------------------

def test_customs_item_trade_sends_range_and_cleans(capsys, keyed_env, monkeypatch):
    # The XML-only service: the CLI cleans by default and never sends the JSON flag.
    urls = _fake_opener(monkeypatch, _xml_envelope(
        [{"year": "2026.01", "hsCode": "8542311000", "statKor": "집적회로",
          "expDlr": "123", "expWgt": "4", "impDlr": "5", "impWgt": "6",
          "balPayments": "118"}], total=1))
    assert main(["customs", "item_trade", "8542",
                 "--start", "202601", "--end", "202603"]) == 0
    out = capsys.readouterr().out
    assert "item_name" in out and "export_usd" in out        # cleaned columns
    assert "2026-01" in out                                  # dotted period parsed
    assert "hsSgn=8542" in urls[0]
    assert "strtYymm=202601" in urls[0] and "endYymm=202603" in urls[0]
    assert "_type=json" not in urls[0] and "resultType=json" not in urls[0]


def test_customs_item_trade_requires_the_range(keyed_env):
    with pytest.raises(SystemExit) as exc:
        main(["customs", "item_trade", "8542"])
    assert exc.value.code == 2


# --- fetch-dispatch paths for the XML services (arg forwarding + render + exit 0) ---------
# These three subcommands wire argparse straight into the service; a rename that moves a flag
# or its dest (as the recent --regid/--time-forecast/--start sweep did) would break the glue
# while the service-level tests stayed green. Each asserts the forwarded filters reach the
# vendor URL, the row renders cleaned, and the exit code is 0.

def test_holidays_dispatches_year_and_month_and_cleans(capsys, keyed_env, monkeypatch):
    urls = _fake_opener(monkeypatch, _xml_envelope(
        [{"dateKind": "01", "dateName": "1월1일", "isHoliday": "Y",
          "locdate": "20260101", "seq": "1"}], total=1))
    assert main(["holidays", "--year", "2026", "--month", "1"]) == 0
    out = capsys.readouterr().out
    assert "is_holiday" in out and "2026-01-01" in out       # cleaned column + parsed date
    assert "solYear=2026" in urls[0] and "solMonth=01" in urls[0]


def test_realestate_dispatches_lawd_code_and_deal_ym_and_cleans(capsys, keyed_env, monkeypatch):
    urls = _fake_opener(monkeypatch, _xml_envelope(
        [{"dealYear": "2024", "dealMonth": "1", "dealDay": "19", "sggCd": "11110",
          "umdNm": "숭인동", "jibun": "766", "aptNm": "종로청계힐스테이트",
          "excluUseAr": "84.9478", "floor": "13", "buildYear": "2009",
          "dealAmount": "101,300"}], total=1))
    assert main(["realestate", "apt_trade", "11110", "--deal-ym", "202401"]) == 0
    out = capsys.readouterr().out
    assert "lawd_code" in out and "2024-01-19" in out        # renamed column + synthesized date
    assert "LAWD_CD=11110" in urls[0] and "DEAL_YMD=202401" in urls[0]


def test_midforecast_dispatches_regid_and_time_forecast_and_cleans(capsys, keyed_env, monkeypatch):
    urls = _fake_opener(monkeypatch, _xml_envelope(
        [{"regId": "11B00000", "rnSt5Am": "20", "wf5Am": "구름많음"}], total=1))
    assert main(["midforecast", "land", "--regid", "11B00000",
                 "--time-forecast", "202608111800"]) == 0
    out = capsys.readouterr().out
    assert "regid" in out and "precip_prob_5am" in out       # renamed column + cleaned field
    assert "regId=11B00000" in urls[0] and "tmFc=202608111800" in urls[0]
    assert "dataType=XML" in urls[0]


# --- procurement / airquality closed-value flags -----------------------------

def test_procurement_rejects_an_invalid_query_basis():
    # --query-basis is a closed set (1/2); argparse choices reject anything else at parse
    # time, before a key is even needed.
    with pytest.raises(SystemExit) as exc:
        main(["procurement", "goods", "--begin", "202608010000",
              "--end", "202608102359", "--query-basis", "9"])
    assert exc.value.code == 2


def test_procurement_omitted_query_basis_uses_the_library_default(keyed_env, monkeypatch):
    # Omitting --query-basis forwards nothing, so fetch's own default ("1" -> inqryDiv=1)
    # applies -- the CLI does not restate it.
    urls = _fake_opener(monkeypatch, _xml_envelope([{"bidNtceNo": "1", "bidNtceOrd": "0"}],
                                                   total=1))
    assert main(["procurement", "goods",
                 "--begin", "202608010000", "--end", "202608102359"]) == 0
    assert "inqryDiv=1" in urls[0]


def test_procurement_query_basis_is_forwarded_only_when_supplied(keyed_env, monkeypatch):
    # A URL check alone can't prove the SUPPRESS delegation -- inqryDiv=1 would appear whether
    # the CLI supplied "1" or the library defaulted to it. Spy on fetch and assert the keyword
    # is absent when the flag is omitted (so the library default applies), present when given.
    seen: dict[str, object] = {}

    def spy(self, name, **kwargs):
        seen.clear()
        seen.update(kwargs)
        return []

    monkeypatch.setattr("pydatagokr.services.procurement.Procurement.fetch", spy)

    assert main(["procurement", "goods",
                 "--begin", "202608010000", "--end", "202608102359"]) == 0
    assert "query_basis" not in seen                     # delegated to the library default

    assert main(["procurement", "goods", "--begin", "202608010000",
                 "--end", "202608102359", "--query-basis", "2"]) == 0
    assert seen["query_basis"] == "2"                    # forwarded exactly as given


def test_airquality_rejects_an_invalid_data_term():
    with pytest.raises(SystemExit) as exc:
        main(["airquality", "by_station", "종로구", "--data-term", "WEEKLY"])
    assert exc.value.code == 2


def test_airquality_data_term_is_forwarded_only_when_supplied(keyed_env, monkeypatch):
    # SUPPRESS: omitting --data-term must forward nothing, so by_station's own default applies;
    # supplying it forwards the value.
    seen: dict[str, object] = {}

    def spy(self, *, station, **kwargs):
        seen.clear()
        seen.update(kwargs)
        return []

    monkeypatch.setattr("pydatagokr.services.airquality.AirQuality.by_station", spy)

    assert main(["airquality", "by_station", "종로구"]) == 0
    assert "data_term" not in seen                        # delegated to the library default

    assert main(["airquality", "by_station", "종로구", "--data-term", "MONTH"]) == 0
    assert seen.get("data_term") == "MONTH"


# --- failures ----------------------------------------------------------------

def test_vendor_error_exits_1(capsys, keyed_env, monkeypatch):
    _fake_opener(monkeypatch, _body({"response": {
        "header": {"resultCode": "99", "resultMsg": "UNKNOWN_ERROR"}, "body": {}}}))
    assert main(["kofia", "market_funds"]) == 1
    assert "datagokr: " in capsys.readouterr().err
