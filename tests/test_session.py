"""The portal envelope contract and paging, offline via an injected fake opener."""

import http.client
import io
import json
import traceback
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message

import pytest

from pydatagokr.errors import (
    DataGoKrAuthError,
    DataGoKrError,
    DataGoKrNetworkError,
    DataGoKrPagingError,
    DataGoKrRateLimitError,
    DataGoKrResponseError,
)
from pydatagokr.session import _PAGE_CAP, DataGoKrSession, _NoRedirect, _retry_after_seconds

_BASE = "https://apis.data.go.kr/0000000/service/TestService"
# A key with reserved characters, so single- vs double-encoding is observable.
_KEY = "raw+key/with==specials"


class _FakeResponse:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._raw


class _ReadFails:
    """A response that opens fine but raises when its body is read (a mid-read failure)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        raise self._exc


class _FakeOpener:
    """Returns canned bodies (or raises canned exceptions), recording each request.

    An outcome may be ``bytes`` (wrapped in a response), an ``Exception`` (raised from
    ``open``), or a pre-built response object (returned as-is, e.g. one whose ``read``
    raises).
    """

    def __init__(self, *outcomes):
        self._outcomes = list(outcomes)
        self.requests = []
        self.timeouts = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, bytes):
            return _FakeResponse(outcome)
        return outcome


class _InfiniteOpener:
    """Returns the same non-empty, count-less body on every call (a runaway series)."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.requests: list[object] = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        return _FakeResponse(self._body)


def _session(*outcomes, **kwargs):
    opener = _FakeOpener(*outcomes)
    return DataGoKrSession(_BASE, _KEY, opener=opener, **kwargs), opener


def _body(payload) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _envelope(items, *, total=None, code="00", message="NORMAL SERVICE."):
    body = {}
    if items is not None:
        body["items"] = {"item": items}
    if total is not None:
        body["totalCount"] = total
    return _body({"response": {"header": {"resultCode": code, "resultMsg": message},
                               "body": body}})


def _fault(code, err_msg="SERVICE ERROR.", auth_msg=None):
    header = {"returnReasonCode": code, "errMsg": err_msg}
    if auth_msg is not None:
        header["returnAuthMsg"] = auth_msg
    return _body({"OpenAPI_ServiceResponse": {"cmmMsgHeader": header}})


def _xml_envelope(items, *, total=None, code="00", message="NORMAL SERVICE."):
    """The XML-only service's envelope -- the same nested shape as ``_envelope`` in XML.
    ``items`` may be ``None`` (no ``<items>``) or a (possibly empty) list of row dicts."""
    parts = [f"<header><resultCode>{code}</resultCode>"
             f"<resultMsg>{message}</resultMsg></header>"]
    body = ""
    if items is not None:
        rows = "".join(
            "<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in item.items()) + "</item>"
            for item in items)
        body += f"<items>{rows}</items>"
    if total is not None:
        body += f"<totalCount>{total}</totalCount>"
    parts.append(f"<body>{body}</body>")
    return f"<response>{''.join(parts)}</response>".encode()


def _xml_fault(code, *, err_msg="SERVICE ERROR.", auth_msg=None):
    header = (f"<returnReasonCode>{code}</returnReasonCode>"
              f"<errMsg>{err_msg}</errMsg>")
    if auth_msg is not None:
        header += f"<returnAuthMsg>{auth_msg}</returnAuthMsg>"
    return (f"<OpenAPI_ServiceResponse><cmmMsgHeader>{header}"
            f"</cmmMsgHeader></OpenAPI_ServiceResponse>").encode()


def _http_error(status):
    # The URL carries the key exactly as the real request URL does (serviceKey=...), so a
    # regression that leaked HTTPError.url into a message would surface the key and trip
    # the secret-safety assertions rather than pass on a harmless placeholder URL.
    url = f"{_BASE}/getThing?serviceKey={urllib.parse.quote_plus(_KEY)}&pageNo=1"
    return urllib.error.HTTPError(url, status, "msg", Message(), io.BytesIO(b""))


# --- request building --------------------------------------------------------

def test_decoding_key_is_single_encoded():
    session, opener = _session(_envelope([], total=0))
    session.fetch("getThing")
    url = opener.requests[0].full_url
    once = urllib.parse.quote_plus(_KEY)
    assert f"serviceKey={once}" in url                       # encoded exactly once
    assert urllib.parse.quote_plus(once) not in url          # never double-encoded
    assert _KEY not in url                                   # reserved chars did escape


def test_request_carries_json_param_paging_and_filters():
    session, opener = _session(_envelope([], total=0))
    session.fetch("getThing", num_of_rows=500, beginBasDt="20240101", endBasDt=None)
    url = opener.requests[0].full_url
    assert url.startswith(f"{_BASE}/getThing?")
    assert "resultType=json" in url
    assert "numOfRows=500" in url and "pageNo=1" in url
    assert "beginBasDt=20240101" in url
    assert "endBasDt" not in url                             # None filters are omitted


def test_underscore_type_json_param():
    session, opener = _session(_envelope([], total=0), json_param="_type")
    session.fetch("getThing")
    assert "_type=json" in opener.requests[0].full_url
    assert "resultType" not in opener.requests[0].full_url


# --- the success envelope ----------------------------------------------------

def test_rows_come_back_as_string_dicts():
    session, _ = _session(_envelope([{"basDt": "20240105", "amt": 1234, "gap": None}],
                                    total=1))
    assert session.fetch("getThing") == [{"basDt": "20240105", "amt": "1234", "gap": ""}]


def test_single_dict_item_is_normalized_to_a_list():
    # A one-row page arrives as a bare object, not a one-element array.
    session, _ = _session(_envelope({"basDt": "20240105"}, total=1))
    assert session.fetch("getThing") == [{"basDt": "20240105"}]


def test_empty_items_marker_is_empty_list():
    # An empty page arrives as items: "" on some services.
    session, _ = _session(_body({"response": {"header": {"resultCode": "00"},
                                              "body": {"items": "", "totalCount": 0}}}))
    assert session.fetch("getThing") == []


def test_paging_follows_total_count():
    session, opener = _session(
        _envelope([{"n": "1"}], total=2),
        _envelope([{"n": "2"}], total=2),
    )
    rows = session.fetch("getThing", num_of_rows=1)
    assert rows == [{"n": "1"}, {"n": "2"}]
    assert len(opener.requests) == 2                         # stopped at totalCount
    assert "pageNo=2" in opener.requests[1].full_url


def test_total_count_beats_a_short_intermediate_page():
    # A service that caps its own page below num_of_rows but reports totalCount: page 1 is
    # SHORT (1 < 1000) yet the count says more, so paging must continue. The old short-page
    # rule would have stopped here and silently truncated to one row.
    session, opener = _session(
        _envelope([{"n": "1"}], total=2),
        _envelope([{"n": "2"}], total=2),
    )
    assert session.fetch("getThing", num_of_rows=1000) == [{"n": "1"}, {"n": "2"}]
    assert len(opener.requests) == 2                         # short page did not end it


def test_missing_total_count_stops_on_the_empty_page():
    session, opener = _session(
        _envelope([{"n": "1"}]),                             # no totalCount at all
        _envelope([], total=None),
    )
    assert session.fetch("getThing", num_of_rows=1) == [{"n": "1"}]
    assert len(opener.requests) == 2


def test_short_page_is_the_last_page():
    # A service that returns the whole result in one call -- fewer than num_of_rows, no
    # totalCount, ignoring pageNo (the customs endpoint) -- must stop after the one
    # request. Without the short-page stop this opener would loop to _PAGE_CAP.
    opener = _InfiniteOpener(_envelope([{"n": "1"}, {"n": "2"}, {"n": "3"}]))
    session = DataGoKrSession(_BASE, _KEY, opener=opener)
    rows = session.fetch("getThing", num_of_rows=1000)
    assert rows == [{"n": "1"}, {"n": "2"}, {"n": "3"}]
    assert len(opener.requests) == 1                         # 3 < 1000 = last page


def test_countless_run_raises_at_the_page_cap():
    # A service that returns a FULL page (num_of_rows rows) every time but never a
    # totalCount could page forever; the runaway guard stops at _PAGE_CAP calls and
    # refuses to return a silently truncated result.
    opener = _InfiniteOpener(_envelope([{"n": "1"}]))       # full page (1 == num_of_rows)
    session = DataGoKrSession(_BASE, _KEY, opener=opener)
    with pytest.raises(DataGoKrPagingError) as exc:         # its own class, not the bare base
        session.fetch("getThing", num_of_rows=1)
    assert len(opener.requests) == _PAGE_CAP
    assert "getThing" in str(exc.value)


def test_empty_page_before_totalcount_refuses_to_truncate():
    # totalCount declares 3 rows, but the 2nd page comes back empty before we reach it. Rather
    # than silently return 2 rows as a complete result, the session refuses.
    session, _ = _session(
        _envelope([{"n": "1"}, {"n": "2"}], total=3),
        _envelope([], total=3),
    )
    with pytest.raises(DataGoKrPagingError) as exc:
        session.fetch("getThing", num_of_rows=2)
    assert "before its declared totalCount" in str(exc.value)


@pytest.mark.parametrize("reserved", ["pageNo", "numOfRows", "serviceKey", "resultType"])
def test_reserved_filter_name_is_rejected(reserved):
    # A filter whose name collides with a transport-managed query param (e.g. pageNo would pin
    # every request to one page and accumulate duplicates) must be rejected, not forwarded.
    session, _ = _session(_envelope([], total=0))
    with pytest.raises(ValueError, match="transport-managed"):
        session.fetch("getThing", **{reserved: "1"})


def test_rate_limit_error_carries_retry_after_seconds():
    headers = Message()
    headers["Retry-After"] = "12"
    err = urllib.error.HTTPError(
        f"{_BASE}/getThing?serviceKey={urllib.parse.quote_plus(_KEY)}", 429, "msg",
        headers, io.BytesIO(b""))
    session, _ = _session(err)
    with pytest.raises(DataGoKrRateLimitError) as exc:
        session.fetch("getThing")
    assert exc.value.retry_after == 12
    # A rate limit is a coded envelope rejection, so `except DataGoKrResponseError` -- the
    # catch-all the auth docstring advertises -- must catch it too, not just DataGoKrError.
    assert isinstance(exc.value, DataGoKrResponseError)
    assert _retry_after_seconds(None) is None and _retry_after_seconds("in a while") is None


def test_non_object_row_raises():
    session, _ = _session(_envelope(["junk"], total=1))
    with pytest.raises(DataGoKrNetworkError):
        session.fetch("getThing")


# --- error-A: the service's own resultCode -----------------------------------

def test_no_data_result_code_is_empty_not_error():
    session, _ = _session(_envelope(None, code="03", message="NODATA_ERROR"))
    assert session.fetch("getThing") == []


def test_other_result_code_raises_response_error():
    session, _ = _session(_envelope(None, code="99", message="UNKNOWN_ERROR"))
    with pytest.raises(DataGoKrResponseError) as exc:
        session.fetch("getThing")
    assert exc.value.code == "99"
    assert "[99]" in str(exc.value)


@pytest.mark.parametrize("code,exc_type", [
    ("1",   DataGoKrResponseError),
    ("4",   DataGoKrResponseError),
    ("30",  DataGoKrAuthError),
    ("030", DataGoKrAuthError),       # 3-digit zero-padded (국토부 RTMS style)
    ("22",  DataGoKrRateLimitError),
    ("022", DataGoKrRateLimitError),  # padded traffic code still backs off, not generic
])
def test_result_code_maps_like_the_portal_fault(code, exc_type):
    # The service-envelope resultCode (error-A) shares the portal's reason vocabulary, so
    # it must map to the same class -- and carry the raw code on .code -- as the fault
    # path, whether the agency zero-pads to two digits or three.
    session, _ = _session(_envelope(None, code=code, message="X"))
    with pytest.raises(exc_type) as exc:
        session.fetch("getThing")
    assert exc.value.code == code


# --- error-B: the portal fault envelope --------------------------------------

def test_fault_30_unregistered_key_raises_auth_error():
    session, _ = _session(_fault("30", auth_msg="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"))
    with pytest.raises(DataGoKrAuthError) as exc:
        session.fetch("getThing")
    assert exc.value.code == "30"


def test_fault_20_missing_key_raises_auth_error():
    session, _ = _session(_fault("20"))
    with pytest.raises(DataGoKrAuthError):
        session.fetch("getThing")


def test_fault_31_expired_deadline_raises_auth_error():
    # 31 = DEADLINE_HAS_EXPIRED: the service-use period lapsed, an access failure like a
    # rejected key, so it maps to the auth error, not a plain response error.
    session, _ = _session(_fault("31", auth_msg="DEADLINE_HAS_EXPIRED_ERROR"))
    with pytest.raises(DataGoKrAuthError):
        session.fetch("getThing")


@pytest.mark.parametrize("code", ["22", "23"])
def test_fault_traffic_codes_raise_rate_limit(code):
    session, _ = _session(_fault(code, auth_msg="LIMITED_NUMBER_OF_SERVICE_REQUESTS"))
    with pytest.raises(DataGoKrRateLimitError) as exc:
        session.fetch("getThing")
    assert exc.value.code == code    # carries the code so 22 (daily) vs 23 (per-second)


def test_fault_other_code_raises_response_error():
    session, _ = _session(_fault("12", err_msg="NO_OPENAPI_SERVICE_ERROR"))
    with pytest.raises(DataGoKrResponseError) as exc:
        session.fetch("getThing")
    assert exc.value.code == "12"


# --- transport failures ------------------------------------------------------

def test_http_429_raises_rate_limit():
    session, _ = _session(_http_error(429))
    with pytest.raises(DataGoKrRateLimitError):
        session.fetch("getThing")


def test_http_500_raises_network_error():
    session, _ = _session(_http_error(500))
    with pytest.raises(DataGoKrNetworkError):
        session.fetch("getThing")


@pytest.mark.parametrize("status", [401, 403])
def test_http_401_403_raise_auth_error(status):
    # The gateway rejects a bad/unregistered key with 401/403 before the reason-code body
    # exists; that is an auth failure (not retryable), not a transient network error.
    session, _ = _session(_http_error(status))
    with pytest.raises(DataGoKrAuthError) as exc:
        session.fetch("getThing")
    assert exc.value.code == str(status)


def test_json_mode_xml_fault_is_classified_by_reason_code():
    # data.go.kr's gateway can return its XML fault at HTTP 200 even when JSON was
    # requested (it faults before applying the json flag); the JSON path must still
    # surface the reason code, not a generic network error.
    session, _ = _session(_xml_fault("30", auth_msg="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"))
    with pytest.raises(DataGoKrAuthError) as exc:
        session.fetch("getThing")
    assert exc.value.code == "30"


def test_urlerror_raises_network_error():
    session, _ = _session(urllib.error.URLError(OSError("name resolution failed")))
    with pytest.raises(DataGoKrNetworkError):
        session.fetch("getThing")


def test_non_json_body_raises_network_error():
    # The portal's XML fault (or a maintenance page) is a non-JSON 200.
    session, _ = _session(b"<OpenAPI_ServiceResponse>...</OpenAPI_ServiceResponse>")
    with pytest.raises(DataGoKrNetworkError):
        session.fetch("getThing")


def test_non_object_json_raises_network_error():
    session, _ = _session(b"[1, 2, 3]")
    with pytest.raises(DataGoKrNetworkError):
        session.fetch("getThing")


@pytest.mark.parametrize("exc", [
    ConnectionResetError("reset"),
    http.client.IncompleteRead(b"partial"),
])
def test_read_failure_raises_network_error(exc):
    # The connection drops after open() succeeds but during response.read().
    session, _ = _session(_ReadFails(exc))
    with pytest.raises(DataGoKrNetworkError):
        session.fetch("getThing")


def test_recursion_error_decoding_raises_network_error(monkeypatch):
    # A pathological body can blow the recursion limit inside json.loads; that must
    # surface as our network error, not escape as a raw RecursionError.
    session, _ = _session(_envelope([{"n": "1"}], total=1))

    def boom(*args, **kwargs):
        raise RecursionError

    monkeypatch.setattr(json, "loads", boom)
    with pytest.raises(DataGoKrNetworkError):
        session.fetch("getThing")


def test_non_utf8_body_raises_network_error():
    session, _ = _session(b"\xff\xfe")                      # not decodable as UTF-8
    with pytest.raises(DataGoKrNetworkError):
        session.fetch("getThing")


# --- the XML transport (an XML-only service like customs) --------------------

def test_xml_rows_match_the_json_path():
    # The XML body decodes into the identical list-of-string-dicts the JSON path yields.
    session, _ = _session(
        _xml_envelope([{"hsCode": "8542", "expDlr": "10"},
                       {"hsCode": "8541", "expDlr": "20"}], total=2),
        response_format="xml")
    assert session.fetch("getThing") == [
        {"hsCode": "8542", "expDlr": "10"},
        {"hsCode": "8541", "expDlr": "20"},
    ]


def test_xml_single_item_is_normalized_to_a_list():
    session, _ = _session(
        _xml_envelope([{"hsCode": "8542"}], total=1), response_format="xml")
    assert session.fetch("getThing") == [{"hsCode": "8542"}]


def test_xml_three_items_keep_all_rows_in_order():
    # The _xml_to_dict list-accumulation `.append` branch only runs from the 3rd repeated
    # <item> onward; a 2-row page never exercises it. All three must survive, in order.
    session, _ = _session(
        _xml_envelope([{"n": "1"}, {"n": "2"}, {"n": "3"}], total=3), response_format="xml")
    assert session.fetch("getThing") == [{"n": "1"}, {"n": "2"}, {"n": "3"}]


def test_custom_timeout_reaches_the_opener():
    # The configured timeout must actually be passed to opener.open (not silently dropped).
    session, opener = _session(_envelope([], total=0), timeout=12.5)
    session.fetch("getThing")
    assert opener.timeouts == [12.5]


def test_json_body_with_a_utf8_bom_is_parsed():
    # Some endpoints prepend a UTF-8 BOM; utf-8-sig strips it so json.loads does not choke.
    body = b"\xef\xbb\xbf" + _envelope([{"basDt": "20240105"}], total=1)
    session, _ = _session(body)
    assert session.fetch("getThing") == [{"basDt": "20240105"}]


def test_xml_empty_items_is_empty_list():
    session, _ = _session(_xml_envelope([], total=0), response_format="xml")
    assert session.fetch("getThing") == []


def test_xml_whitespace_only_items_is_empty_list():
    # A pretty-printed empty <items> block is whitespace text, not "", so the empty-marker
    # check must treat a blank string as no rows -- otherwise a legitimately empty result
    # surfaces as a "non-object row" network error.
    body = (b"<response><header><resultCode>00</resultCode>"
            b"<resultMsg>NORMAL SERVICE.</resultMsg></header>"
            b"<body><items>\n      </items><totalCount>0</totalCount></body></response>")
    session, _ = _session(body, response_format="xml")
    assert session.fetch("getThing") == []


def test_xml_fault_maps_like_the_json_fault():
    session, _ = _session(
        _xml_fault("30", auth_msg="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"),
        response_format="xml")
    with pytest.raises(DataGoKrAuthError) as exc:
        session.fetch("getThing")
    assert exc.value.code == "30"


def test_malformed_xml_raises_network_error_without_the_key():
    session, _ = _session(b"<response><header>", response_format="xml")
    with pytest.raises(DataGoKrNetworkError) as exc:
        session.fetch("getThing")
    assert _KEY not in str(exc.value)
    assert urllib.parse.quote_plus(_KEY) not in str(exc.value)
    assert exc.value.__cause__ is None                       # the parser chain is broken
    assert exc.value.__context__ is None


def test_xml_mode_omits_the_json_param():
    session, opener = _session(_xml_envelope([], total=0), response_format="xml")
    session.fetch("getThing")
    url = opener.requests[0].full_url
    assert "_type=json" not in url and "resultType=json" not in url
    assert "serviceKey=" in url and "numOfRows=" in url and "pageNo=1" in url


# --- the secret never appears ------------------------------------------------

# Nests well past sys.recursionlimit; on the supported CPython matrix (3.11-3.14) this raises
# RecursionError (not a C-stack segfault), which the session catches as DataGoKrNetworkError.
_DEEP_XML = (b"<r>" * 3000 + b"x" + b"</r>" * 3000)


def _failing_sessions():
    # Every failure branch of the transport, each carrying the key in its request URL, so a
    # regression that let the URL reach a message/traceback or chained a key-bearing
    # exception would surface the key here. Covers: HTTP status errors (incl. redirect and
    # rate-limit), URLError, a mid-read HTTPException/OSError, a body that is neither JSON
    # nor XML, invalid UTF-8, a body that over-nests the XML walk, both fault envelopes
    # (JSON and XML), the error-A resultCode path, and the package-built failures that carry
    # no vendor text (an unexpected response shape, a non-object row). The paging-cap error
    # takes a different call and has its own secret test below.
    return [
        _session(_http_error(500))[0],
        _session(_http_error(429))[0],
        _session(_http_error(302))[0],
        _session(urllib.error.URLError(OSError("dns")))[0],
        _session(_ReadFails(http.client.IncompleteRead(b"")))[0],
        _session(_ReadFails(ConnectionResetError("reset")))[0],
        _session(b"{not json and not xml")[0],
        _session(b"\xff\xfe\x00 not utf-8")[0],
        _session(_DEEP_XML)[0],
        _session(_fault("30", auth_msg="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"))[0],
        _session(_envelope(None, code="99", message="UNKNOWN_ERROR"))[0],
        _session(_body({"unexpected": "shape"}))[0],          # dict, but no response/fault key
        _session(_body(["unexpected", "shape"]))[0],          # top-level JSON is not an object
        _session(_envelope(["not-a-dict-row"], total=1))[0],  # items.item is not an object
        _session(_xml_fault("30", auth_msg="BAD"), response_format="xml")[0],
        _session(b"<response><header>", response_format="xml")[0],
        _session(_DEEP_XML, response_format="xml")[0],
    ]


def test_key_never_appears_in_any_error():
    # The key must be absent -- raw, query-encoded (quote_plus), and path-encoded (quote) --
    # from BOTH the exception message and the full formatted traceback (which would include
    # any chained __cause__/__context__), and the chain must be detached.
    forms = [_KEY, urllib.parse.quote_plus(_KEY), urllib.parse.quote(_KEY)]
    for session in _failing_sessions():
        with pytest.raises(DataGoKrError) as exc:
            session.fetch("getThing")
        tb = "".join(traceback.format_exception(
            type(exc.value), exc.value, exc.value.__traceback__))
        for form in forms:
            assert form not in str(exc.value)
            assert form not in tb
            assert form not in repr(exc.value.args)          # not hiding in an extra arg
        assert exc.value.__cause__ is None                   # the chain is broken
        assert exc.value.__context__ is None


def test_paging_cap_error_never_shows_the_key():
    # The paging-cap failure is package-built (never from vendor text or the URL), but it is
    # still raised on a key-bearing request, so hold it to the same secret invariant. It takes
    # a paging call rather than the single fetch the matrix above uses.
    opener = _InfiniteOpener(_envelope([{"n": "1"}]))       # a full page forever -> hits the cap
    session = DataGoKrSession(_BASE, _KEY, opener=opener)
    with pytest.raises(DataGoKrPagingError) as exc:
        session.fetch("getThing", num_of_rows=1)
    tb = "".join(traceback.format_exception(
        type(exc.value), exc.value, exc.value.__traceback__))
    for form in (_KEY, urllib.parse.quote_plus(_KEY), urllib.parse.quote(_KEY)):
        assert form not in str(exc.value)
        assert form not in tb
        assert form not in repr(exc.value.args)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


def test_scheme_less_or_http_base_url_is_rejected_without_leaking_the_key():
    # A scheme-less base_url makes urllib build the key-bearing Request OUTSIDE the transport's
    # try/except, surfacing the full URL (serviceKey=...) in a bare ValueError; an http:// root
    # would ship the key in cleartext. Both must be refused at construction -- before any
    # request -- and the error must carry no form of the key. README Sec.2.2 tells users to
    # paste the portal's request URL into DataGoKrSession(...), so a missing scheme is expected.
    forms = [_KEY, urllib.parse.quote_plus(_KEY), urllib.parse.quote(_KEY)]
    for bad in ("apis.data.go.kr/0000000/service", "http://apis.data.go.kr/0000000/service"):
        with pytest.raises(ValueError) as exc:
            DataGoKrSession(bad, _KEY)
        for form in forms:
            assert form not in str(exc.value)


def test_https_base_url_is_accepted():
    # The valid case still constructs (a plain https root), so the guard rejects only bad schemes.
    assert DataGoKrSession("https://apis.data.go.kr/x", _KEY).base_url == "https://apis.data.go.kr/x"


def test_transport_config_is_read_only_after_construction():
    # base_url is validated as https BEFORE the key is resolved; if it stayed settable a caller
    # could repoint the session -- and the key-bearing query string -- at http after that check.
    # It and its siblings are read-only properties, so assignment raises rather than reopening
    # the leak the scheme guard closes.
    session = DataGoKrSession("https://apis.data.go.kr/x", _KEY)
    for attr in ("base_url", "timeout", "json_param", "response_format"):
        with pytest.raises(AttributeError):
            setattr(session, attr, "http://evil.example")


def test_over_collected_paging_refuses_to_return_duplicates():
    # A vendor that declares a totalCount but ignores pageNo re-serves the same full page every
    # request; collecting past the count would silently return duplicates, so refuse it -- the
    # mirror of the empty-page-before-total refusal.
    opener = _InfiniteOpener(_envelope([{"n": "1"}, {"n": "2"}], total=3))
    session = DataGoKrSession(_BASE, _KEY, opener=opener)
    with pytest.raises(DataGoKrPagingError):
        session.fetch("getThing", num_of_rows=2)


def test_mid_stream_no_data_page_reports_truncation_not_over_count():
    # A service reports totalCount, then answers a later page with resultCode 03 (no data)
    # before the count is reached. Refusing is right, but a no-data page carries no
    # authoritative count, so the latched totalCount must stand and the message must blame
    # truncation -- not misattribute it to over-collection ("more rows than ... (2 > 0)").
    session, _ = _session(
        _envelope([{"n": "1"}, {"n": "2"}], total=5),        # page 1: 2 of 5
        _envelope(None, code="03", message="NODATA_ERROR"),  # page 2: no-data mid-result
    )
    with pytest.raises(DataGoKrPagingError) as exc:
        session.fetch("getThing", num_of_rows=2)
    assert "before its declared totalCount" in str(exc.value)   # truncation, the real cause
    assert "more rows than" not in str(exc.value)               # not the over-count message


def test_total_count_latches_when_a_later_page_omits_it():
    # A vendor reports totalCount on page 1 but omits it on page 2 while re-serving the same
    # full page (ignores pageNo). The latched count still catches the duplication at once,
    # instead of losing the count and running all the way to the page cap.
    session, _ = _session(
        _envelope([{"n": "1"}, {"n": "2"}], total=3),   # page 1: 2 of 3, count present
        _envelope([{"n": "1"}, {"n": "2"}]),            # page 2: same rows, count omitted
    )
    with pytest.raises(DataGoKrPagingError) as exc:
        session.fetch("getThing", num_of_rows=2)
    assert "more rows than its declared totalCount" in str(exc.value)


def test_over_nested_body_becomes_a_network_error_not_a_recursion_error():
    # A pathological deeply-nested body must surface as our network error, not leak a bare
    # RecursionError from the XML walk.
    for mode in ("json", "xml"):
        session, _ = _session(_DEEP_XML, response_format=mode)
        with pytest.raises(DataGoKrNetworkError):
            session.fetch("getThing")


def test_redirect_handler_refuses_and_never_follows_the_target():
    # The redirect handler itself must refuse rather than reissue the key-bearing request to
    # a server-named target: refusing turns a 3xx into an HTTPError (surfaced as a network
    # error) so the key never leaves the original host. Exercised directly, so removing the
    # handler cannot leave this green.
    req = urllib.request.Request(f"https://apis.data.go.kr/svc/op?serviceKey={_KEY}")
    with pytest.raises(urllib.error.HTTPError) as exc:
        _NoRedirect().redirect_request(
            req, io.BytesIO(b""), 302, "Found",
            http.client.HTTPMessage(), "http://evil.example/steal")
    assert exc.value.code == 302
    assert "evil.example" not in str(exc.value)              # never points at the target


def test_vendor_message_echoing_the_key_is_redacted():
    # The portal error text is external; if it echoes the key (raw or encoded), the
    # session must scrub it before it reaches the message.
    encoded = urllib.parse.quote_plus(_KEY)
    session, _ = _session(_fault("31", err_msg=f"bad request {_KEY} / {encoded}"))
    with pytest.raises(DataGoKrResponseError) as exc:
        session.fetch("getThing")
    assert _KEY not in str(exc.value)
    assert encoded not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)


def test_vendor_message_echoing_the_path_encoded_key_is_redacted():
    # The path-encoded form (quote, '/' left intact) differs from the query form
    # (quote_plus); the session must scrub that representation too.
    path_encoded = urllib.parse.quote(_KEY)
    assert path_encoded != urllib.parse.quote_plus(_KEY)     # the two forms really differ
    session, _ = _session(_fault("31", err_msg=f"bad request {path_encoded}"))
    with pytest.raises(DataGoKrResponseError) as exc:
        session.fetch("getThing")
    assert path_encoded not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)


def test_repr_never_shows_the_key():
    session, _ = _session()
    assert _KEY not in repr(session)


# --- construction ------------------------------------------------------------

@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), "30", True])
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(ValueError):
        DataGoKrSession(_BASE, _KEY, timeout=timeout)


@pytest.mark.parametrize("num_of_rows", [0, -1, True, 3.5, "100"])
def test_invalid_num_of_rows_is_rejected(num_of_rows):
    session, _ = _session(_envelope([], total=0))
    with pytest.raises(ValueError):
        session.fetch("getThing", num_of_rows=num_of_rows)


def test_base_url_trailing_slash_is_normalized():
    opener = _FakeOpener(_envelope([], total=0))
    slashed = DataGoKrSession(_BASE + "/", _KEY, opener=opener)
    slashed.fetch("getThing")
    assert opener.requests[0].full_url.startswith(f"{_BASE}/getThing?")
