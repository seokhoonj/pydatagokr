"""DataGoKrSession -- the neutral data.go.kr transport: key injection, paging, envelopes.

One session speaks to one service base URL and turns an operation + filters into rows: a
``list[dict[str, str]]``, the vendor's items passed through with their own field names.
No third-party HTTP client -- ``urllib`` carries it, so the package has zero runtime
dependencies.

The transport is *neutral*: it knows the portal's two envelope shapes and its paging
protocol, and nothing about any particular dataset. It speaks either encoding -- JSON
(the default) or XML, for XML-only services -- and both share one nested shape, so the
XML path parses into the same nested dict the JSON path yields and the envelope logic
below is written once. The success and error-A shape is ``response.header.resultCode``
(``00`` ok, ``03`` no-data) with rows at ``response.body.items.item``; the error-B shape
is the portal fault ``OpenAPI_ServiceResponse.cmmMsgHeader`` with a ``returnReasonCode``.
``fetch`` pages through ``pageNo``/``numOfRows`` until ``totalCount`` rows are collected
(or a page comes back empty, for services that omit the count).

**The secret-safety invariant lives here.** The portal takes the service key as the
``serviceKey`` query parameter, so the request URL contains it. A transport exception's
string, its ``.url`` attribute, and a chained traceback all embed that URL -- so this
module never builds a message from a transport exception's text and never chains one
(``raise ... from None``). Error messages are built from the HTTP status, redacted
vendor-controlled JSON fields, and the operation path *without* its query string.
``__repr__`` never shows the key.

The key must be the portal's **decoding** (raw) form: parameters are url-encoded exactly
once here, so the pre-escaped encoding form would go out double-encoded and be rejected.
"""

from __future__ import annotations

import http.client
import json
import math
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import IO, Any, Protocol, cast

from ._config import resolve_api_key
from .errors import (
    DataGoKrAuthError,
    DataGoKrError,
    DataGoKrNetworkError,
    DataGoKrPagingError,
    DataGoKrRateLimitError,
    _error_for,
)
from .types import JSONParam, ResponseFormat, Row

__all__ = ["DataGoKrSession"]

_USER_AGENT = "pydatagokr"
_RATE_LIMIT_STATUS = 429
_AUTH_STATUSES = frozenset({401, 403})   # gateway rejects a bad/unregistered key here
_OK_CODE = "00"
_NO_DATA_CODE = "03"
_PAGE_CAP = 1000   # runaway guard: 1000 pages x default 1000 rows covers any series


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect instead of following it.

    ``urllib`` follows a 3xx automatically and reissues the request to the new location
    -- carrying the key-bearing query string to whatever host the server names, in
    cleartext on an https -> http downgrade. Refusing turns any redirect into an
    ``HTTPError`` that the session surfaces as :class:`DataGoKrNetworkError`; the key
    never leaves the original https host.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        # The redirect target is server-controlled -- keep it out of the error so nothing
        # it carries can surface through the chained exception.
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


# One private opener for the package: the default global opener follows redirects, so a
# private opener with the no-redirect handler is what actually closes the leak.
_OPENER = urllib.request.build_opener(_NoRedirect)


class _Response(Protocol):
    """What the opener's ``open`` must return: a context manager whose body is bytes."""

    def read(self) -> bytes: ...
    def __enter__(self) -> _Response: ...
    def __exit__(self, *exc: object) -> object: ...


class _Opener(Protocol):
    """The one seam the session lets a caller substitute -- anything that opens a request
    and returns a :class:`_Response`. The package's no-redirect opener satisfies it; an
    offline test hands in a fake returning canned bytes with no network."""

    def open(self, request: urllib.request.Request, timeout: float) -> _Response: ...


class DataGoKrSession:
    """Holds the service key and one base URL; fetches operations as raw rows.

    ``base_url`` is the service root (e.g. the KOFIA statistics service URL) and
    ``operation`` in :meth:`fetch` is the path segment under it. ``response_format`` picks
    the reply encoding: ``"json"`` (the default, a JSON service like KOFIA) sends the
    ``json_param`` "answer in JSON" flag (``resultType`` for older services, ``_type`` for
    newer ones); ``"xml"`` (an XML-only service like customs) omits that flag entirely and
    parses the XML into the same nested shape. The key comes from ``api_key``, then
    ``$DATAGOKR_API_KEY``, then ``~/.config/pydatagokr/credentials.json``; construction
    raises :class:`DataGoKrConfigError` when none of them supplies one.
    """

    def __init__(self, base_url: str, api_key: str | None = None, *,
                 timeout: float = 30.0, json_param: JSONParam = "resultType",
                 response_format: ResponseFormat = "json",
                 opener: _Opener | None = None) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("timeout must be a finite positive number")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number")
        # The key travels in the query string, so base_url MUST be https and carry a scheme
        # BEFORE it is ever embedded in a request URL. A scheme-less value makes urllib's
        # Request(f"{base_url}/...?serviceKey=<KEY>&...") raise ValueError("unknown url type:
        # '<the full key-bearing URL>'") -- built outside _fetch_page's try/except, so it
        # escapes the transport's from-None discipline and surfaces the key. An http:// value
        # would ship the key in cleartext, the exact leak _NoRedirect exists to prevent. All
        # data.go.kr roots are https, so reject anything else at construction, before the key
        # can reach a string.
        if urllib.parse.urlsplit(base_url).scheme != "https":
            raise ValueError(
                "base_url must be an https:// data.go.kr service root "
                "(e.g. 'https://apis.data.go.kr/...')")
        self._base_url = base_url.rstrip("/")
        self._timeout = float(timeout)
        self._json_param: JSONParam = json_param
        self._response_format: ResponseFormat = response_format
        self._api_key = resolve_api_key(api_key)
        self._opener = opener if opener is not None else cast(_Opener, _OPENER)

    def __repr__(self) -> str:
        # Never shows the service key, in whole or in part.
        return "DataGoKrSession(...)"

    # The transport config is validated once at construction and then read-only. base_url
    # in particular is checked for the https scheme BEFORE the key is resolved (see
    # __init__); exposing it as a settable attribute would let a caller repoint the session
    # -- and the key-bearing query string -- at an http or arbitrary host after that check,
    # reopening the exact leak the scheme guard closes. Read-only properties keep the
    # values inspectable without that hole.
    @property
    def base_url(self) -> str:
        """The https service root, fixed at construction (read-only)."""
        return self._base_url

    @property
    def timeout(self) -> float:
        """The per-request timeout in seconds, fixed at construction (read-only)."""
        return self._timeout

    @property
    def json_param(self) -> JSONParam:
        """The 'answer in JSON' query flag this service takes (read-only)."""
        return self._json_param

    @property
    def response_format(self) -> ResponseFormat:
        """The reply encoding this session parses (read-only)."""
        return self._response_format

    def fetch(self, operation: str, *, num_of_rows: int = 1000,
              **filters: str | None) -> list[Row]:
        """Every row of ``operation`` over the given filters, with the vendor's own field
        names. ``filters`` with a ``None`` value are dropped, so an unset date bound is
        simply omitted. Pages until the last page; a no-data result (``resultCode`` 03) is
        an empty list, not an error. ``num_of_rows`` is the page size, not a result cap.

        The last page is recognized three ways, so this works across services that page,
        report a ``totalCount``, or do neither: an empty page, a *short* page (fewer than a
        full ``num_of_rows`` -- the universal last-page signal, and the only one a service
        gives when it returns the whole result at once and omits both paging and the count,
        as the customs endpoint does), or once ``totalCount`` rows have been collected.

        Filter values (date bounds, an HS code, ...) are passed to the vendor unvalidated:
        the vendor is the authority on its own filter grammar, so this transport checks
        only its own inputs (e.g. the timeout, the page size) and forwards the filters as given.
        """
        if isinstance(num_of_rows, bool) or not isinstance(num_of_rows, int) or num_of_rows <= 0:
            raise ValueError("num_of_rows must be a positive integer")
        # serviceKey / numOfRows / pageNo (and the JSON flag) are set by the transport itself;
        # a filter of the same name would overwrite them -- e.g. pageNo would pin every request
        # to one page and silently accumulate duplicate rows -- so reject the collision loudly.
        reserved = {"serviceKey", "numOfRows", "pageNo", self._json_param} & filters.keys()
        if reserved:
            raise ValueError(
                f"filter {sorted(reserved)} collides with a transport-managed query parameter "
                f"(serviceKey/numOfRows/pageNo and the JSON flag are set by the session)")
        rows: list[Row] = []
        for page in range(1, _PAGE_CAP + 1):
            page_rows, total = self._fetch_page(operation, page, num_of_rows, filters)
            rows.extend(page_rows)
            # When the service reports a totalCount it is authoritative: a page shorter
            # than num_of_rows can be a mid-result page from a service that caps its own
            # page size, so a short page must not end paging while the count says rows
            # remain. Without a count, a short (or empty) page is the only last-page signal.
            if total is not None:
                if len(rows) >= total:
                    if len(rows) > total:
                        # More rows than the service declared: a vendor that ignores pageNo and
                        # re-serves a full page every request inflates the result with duplicates.
                        # Symmetric to the empty-page-before-total refusal below -- refuse a
                        # possibly duplicated result rather than return one that looks complete.
                        raise DataGoKrPagingError(
                            f"data.go.kr returned more rows than its declared totalCount "
                            f"({len(rows)} > {total}) for {operation}; refusing a possibly "
                            f"duplicated result")
                    return rows                    # collected exactly the declared count
                if not page_rows:
                    # An empty page BEFORE the declared count is reached is a broken vendor
                    # sequence, not the end -- returning here would silently truncate to a
                    # complete-looking partial result, so refuse it (like the page cap below).
                    raise DataGoKrPagingError(
                        f"data.go.kr returned an empty page for {operation} before its "
                        f"declared totalCount ({len(rows)} of {total} rows); refusing a "
                        f"possibly truncated result")
            elif not page_rows or len(page_rows) < num_of_rows:
                return rows                        # no count: a short/empty page is the end
        # The cap was reached without any last-page signal: rather than silently return a
        # truncated result that looks complete, refuse it. The message carries the
        # operation path only (never the key-bearing query string).
        raise DataGoKrPagingError(
            f"data.go.kr paging for {operation} exceeded {_PAGE_CAP} pages without a "
            f"last-page signal; refusing to return a possibly truncated result")

    def _fetch_page(self, operation: str, page: int, num_of_rows: int,
                    filters: dict[str, str | None]) -> tuple[list[Row], int | None]:
        """One page of ``operation``: ``(rows, totalCount-or-None)``."""
        params: dict[str, str] = {
            "serviceKey": self._api_key,   # the raw decoding key, as a plain value
            "numOfRows":  str(num_of_rows),
            "pageNo":     str(page),
        }
        # A JSON service takes the "answer in JSON" flag; an XML-only service faults if it
        # is sent at all, so xml mode omits it and gets XML back.
        if self._response_format == "json":
            params[self._json_param] = "json"
        params.update({name: value for name, value in filters.items() if value is not None})
        # urlencode exactly once: the raw key goes in as a plain value and comes out
        # single-encoded. Never pre-encode it (the portal's "encoding key" form would be
        # double-encoded here and rejected).
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{self._base_url}/{operation}?{query}", headers={"User-Agent": _USER_AGENT})
        failure: DataGoKrError
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as err:
            # Build the package error while the response is open, then raise it after
            # leaving the except block: that releases the socket and detaches both
            # __cause__ and __context__ from the key-bearing HTTPError.
            with err:
                if err.code == _RATE_LIMIT_STATUS:
                    failure = DataGoKrRateLimitError(
                        "429", f"data.go.kr rate-limited {operation} (HTTP 429)",
                        retry_after=_retry_after_seconds(err.headers.get("Retry-After")))
                elif err.code in _AUTH_STATUSES:
                    # The gateway rejects a bad/unregistered key with 401/403 before the
                    # reason-code body is ever produced; that is an auth failure, not a
                    # transient network one, so it must not be retried.
                    failure = DataGoKrAuthError(
                        str(err.code),
                        f"data.go.kr rejected the service key for {operation} (HTTP {err.code})")
                else:
                    failure = DataGoKrNetworkError(
                        f"HTTP {err.code} from data.go.kr for {operation}")
        except urllib.error.URLError as err:
            # A transport reason is external text and may contain the request URL. Keep
            # only its type, then detach the original exception below.
            failure = DataGoKrNetworkError(
                f"request to data.go.kr failed for {operation}: {type(err.reason).__name__}")
        except (http.client.HTTPException, OSError) as err:
            # A failure during response.read() (IncompleteRead, a socket timeout or
            # reset) is not an HTTPError/URLError; surface it through our error too.
            failure = DataGoKrNetworkError(
                f"data.go.kr response read failed for {operation}: {type(err).__name__}")
        else:
            return self._page_from_body(raw, operation)
        raise failure from None

    def _page_from_body(self, raw: bytes, operation: str) -> tuple[list[Row], int | None]:
        """Apply the portal envelope contract to a raw 200 body (JSON or XML). Both
        encodings decode into the same nested dict, so the envelope logic below runs once
        regardless of the wire format."""
        payload: object
        if self._response_format == "xml":
            payload = self._payload_from_xml(raw, operation)
        else:
            payload = self._payload_from_json(raw, operation)
        if isinstance(payload, dict):
            return self._page_from_payload(payload, operation)
        raise DataGoKrNetworkError(
            f"unexpected data.go.kr response shape for {operation}") from None

    def _payload_from_json(self, raw: bytes, operation: str) -> object:
        """The JSON body as a nested object, or our network error (cause detached). The
        failure is built inside the handler and raised after leaving it, so neither
        ``__cause__`` (``from None``) nor ``__context__`` carries the decode exception."""
        failure: DataGoKrError
        try:
            # parse_int/parse_float=str keep every JSON number as its original text, so a big
            # integer or a scientific-notation amount is not routed through a lossy float
            # before _integer sees it (every vendor value is a string anyway -- the XML path
            # already yields only strings, so this keeps the two encodings symmetric).
            # utf-8-sig strips a leading BOM (some endpoints prepend one) which plain json
            # would reject; a BOM-less body decodes identically.
            return json.loads(raw.decode("utf-8-sig"), parse_int=str, parse_float=str)
        except (ValueError, UnicodeDecodeError, RecursionError):
            # A 200 whose body is not JSON is usually the portal's XML fault envelope --
            # the gateway can fault (unregistered key, traffic limit) before it applies
            # the json flag. Parse it as XML so the reason code still routes to
            # _error_from_fault; only if it is not XML either do we give up (a
            # proxy/maintenance page), cause detached.
            try:
                root = ET.fromstring(raw.decode("utf-8"))
                payload = {root.tag: _xml_to_dict(root)}
            except (ET.ParseError, UnicodeDecodeError, RecursionError):
                failure = DataGoKrNetworkError(
                    f"non-JSON response from data.go.kr for {operation}")
            else:
                return payload
        raise failure from None

    def _payload_from_xml(self, raw: bytes, operation: str) -> dict[str, Any]:
        """The XML body as the SAME nested dict the JSON path yields (root tag wrapped),
        or our network error. The message is FIXED -- never the parser's text or the body
        -- and the parser exception is detached from both ``__cause__`` and ``__context__``
        (built in the handler, raised after it), the same secret-safety discipline as the
        JSON path."""
        failure: DataGoKrError
        try:
            root = ET.fromstring(raw.decode("utf-8"))
            payload = {root.tag: _xml_to_dict(root)}
        except (ET.ParseError, UnicodeDecodeError, RecursionError):
            failure = DataGoKrNetworkError(
                f"non-XML response from data.go.kr for {operation}")
        else:
            return payload
        raise failure from None

    def _page_from_payload(self, payload: dict[str, Any],
                           operation: str) -> tuple[list[Row], int | None]:
        # Error-B: the portal fault envelope, sent when the portal itself rejects the
        # call (unregistered key, traffic limit) before the service ever runs.
        fault = payload.get("OpenAPI_ServiceResponse")
        if isinstance(fault, dict):
            raise self._error_from_fault(fault, operation) from None

        # Success and error-A share one envelope: response.header.resultCode.
        envelope = payload.get("response")
        if not isinstance(envelope, dict):
            raise DataGoKrNetworkError(
                f"unexpected data.go.kr response shape for {operation}") from None
        raw_header = envelope.get("header")
        header: dict[str, Any] = raw_header if isinstance(raw_header, dict) else {}
        code = str(header.get("resultCode", "?")).strip()
        # Agencies zero-pad the result code differently -- the standard is two digits
        # ("00" ok, "03" no-data) but some (국토부 RTMS) send three ("000"/"003"). Compare on
        # the significant digits so both conventions read the same; the original code is
        # kept for the error message.
        digits = code.lstrip("0") or "0"
        if digits == (_NO_DATA_CODE.lstrip("0") or "0"):
            return [], 0    # "no data" is an empty series, not an error
        if digits != (_OK_CODE.lstrip("0") or "0"):
            message = self._redact(str(header.get("resultMsg", "")).strip())
            raise _error_for(code, message) from None

        raw_body = envelope.get("body")
        body: dict[str, Any] = raw_body if isinstance(raw_body, dict) else {}
        return self._rows_from_items(body.get("items"), operation), _total_count(body)

    def _rows_from_items(self, items: object, operation: str) -> list[Row]:
        """Normalize ``body.items.item`` -- a list of objects, a single object (a one-row
        page), or an empty marker (absent, ``""``, a whitespace-only string, or ``{}``) --
        into a list of string rows."""
        item = items.get("item") if isinstance(items, dict) else items
        # An empty items block is the missing-marker: absent, "" (compact <items/>), a
        # whitespace-only string (a pretty-printed <items>\n  </items>), or {}.
        if item is None or (isinstance(item, str) and not item.strip()) or item == {}:
            return []
        raw_rows = item if isinstance(item, list) else [item]
        rows: list[Row] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                raise DataGoKrNetworkError(
                    f"a non-object row from data.go.kr for {operation}") from None
            rows.append({str(key): "" if value is None else str(value)
                         for key, value in row.items()})
        return rows

    def _error_from_fault(self, fault: dict[str, Any], operation: str) -> DataGoKrError:
        """Map an ``OpenAPI_ServiceResponse.cmmMsgHeader`` fault to the right error."""
        raw_header = fault.get("cmmMsgHeader")
        header: dict[str, Any] = raw_header if isinstance(raw_header, dict) else {}
        code = str(header.get("returnReasonCode", "?")).strip()
        message = self._redact(
            str(header.get("returnAuthMsg") or header.get("errMsg") or "").strip())
        return _error_for(code, message or f"portal fault for {operation}")

    def _redact(self, text: str) -> str:
        """Remove raw and query-encoded forms of the key from external error text."""
        redacted = text
        for representation in {self._api_key,
                               urllib.parse.quote_plus(self._api_key),
                               urllib.parse.quote(self._api_key)}:
            if representation:
                redacted = redacted.replace(representation, "[REDACTED]")
        return redacted


def _xml_to_dict(elem: ET.Element) -> dict[str, Any] | str:
    """One XML element as the nested-dict shape the JSON path produces.

    A leaf (no children) becomes its text (``""`` when the element is empty), and a parent
    becomes a dict keyed by child tag. A repeated child tag accumulates into a LIST, so
    ``<items>`` with many ``<item>`` becomes ``{"item": [..]}`` while a lone ``<item>``
    stays ``{"item": {..}}`` -- exactly the two shapes :meth:`_rows_from_items` already
    normalizes -- and an empty ``<items/>`` becomes ``""``, which it treats as no rows.
    Every value is a ``str`` (XML text) or a nested dict; the ``_rows_from_items``
    str-coercion downstream is left in place.
    """
    children = list(elem)
    if not children:
        return elem.text if elem.text is not None else ""
    result: dict[str, Any] = {}
    for child in children:
        value = _xml_to_dict(child)
        if child.tag in result:
            existing = result[child.tag]
            if isinstance(existing, list):
                existing.append(value)
            else:
                result[child.tag] = [existing, value]
        else:
            result[child.tag] = value
    return result


def _retry_after_seconds(value: str | None) -> int | None:
    """The ``Retry-After`` header as a non-negative integer of seconds, or ``None``. Only the
    delta-seconds form is read; the HTTP-date form (rare for a rate limit) is ignored rather
    than parsed, so a caller that gets ``None`` simply falls back to its own backoff."""
    if value is None:
        return None
    try:
        seconds = int(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _total_count(body: dict[str, Any]) -> int | None:
    """``body.totalCount`` as an int, or ``None`` when absent or unparsable -- the caller
    then falls back to the empty-page stop rather than treating a missing count as
    'done'."""
    raw_total = body.get("totalCount")
    if raw_total is None:
        return None
    try:
        return int(raw_total)
    except (TypeError, ValueError):
        return None
