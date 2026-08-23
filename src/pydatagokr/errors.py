"""Exception hierarchy for pydatagokr.

Every operational error this package raises derives from :class:`DataGoKrError`, so one
``except DataGoKrError`` catches them all. The subclasses separate the failure modes a
caller handles differently: a misconfiguration caught before any request
(:class:`DataGoKrConfigError`), a rejected or un-applied service key
(:class:`DataGoKrAuthError`), a traffic-limit rejection (:class:`DataGoKrRateLimitError`),
any other vendor-reported error inside a well-formed response
(:class:`DataGoKrResponseError`), a transport failure that never produced a portal body
(:class:`DataGoKrNetworkError`), and a paging run that never saw a last-page signal
(:class:`DataGoKrPagingError`). Invalid *caller* input -- an unknown operation name
-- raises ``ValueError``, the usual signal for a caller mistake rather than a runtime
failure.

data.go.kr signals failure two ways: the service's own JSON envelope with a non-``00``
``resultCode`` (the error-A shape), or the portal fault envelope
``OpenAPI_ServiceResponse.cmmMsgHeader`` with a ``returnReasonCode`` (the error-B shape,
sent when the portal itself rejects the call -- an unregistered key, a traffic limit).
:func:`_error_for` turns either shape's code into the right subclass.

The service key travels in the query string, so **no error message here is ever built
from a transport exception's string or a request URL** -- those embed the key. Messages
are built from safe structured fields only (the HTTP status, redacted vendor message
fields, the operation path), and the cause chain is broken at the raise site (see
:mod:`pydatagokr.session`).
"""

from __future__ import annotations

# The portal's common reason-code vocabulary (cmmMsgHeader.returnReasonCode), which a
# service's own resultCode also draws from. The full set data.go.kr documents:
#   1  APPLICATION_ERROR            portal server fault      -> DataGoKrResponseError
#   4  HTTP_ERROR                   provider server fault    -> DataGoKrResponseError
#   12 NO_OPENAPI_SERVICE_ERROR     service gone / deprecated-> DataGoKrResponseError
#   20 SERVICE_ACCESS_DENIED_ERROR  not applied / suspended  -> DataGoKrAuthError
#   22 traffic (daily) exceeded                              -> DataGoKrRateLimitError
#   23 per-second throttle                                   -> DataGoKrRateLimitError
#   30 SERVICE_KEY_IS_NOT_REGISTERED bad key / apply not done-> DataGoKrAuthError
#   31 DEADLINE_HAS_EXPIRED         service period expired   -> DataGoKrAuthError
#   99 UNKNOWN_ERROR                other                    -> DataGoKrResponseError
# Anything not classified below falls through to DataGoKrResponseError, which preserves
# the vendor code on `.code` so a caller can still branch on 1/4/12/99 itself.
# Reason codes that mean the key or the dataset access was rejected:
_AUTH_REASON_CODES = frozenset({"20", "30", "31"})
# Reason codes that mean the call volume was rejected: 22 = daily traffic limit,
# 23 = concurrent/per-second throttle. Neither should be retried immediately (22 resets
# at midnight KST).
_RATE_LIMIT_REASON_CODES = frozenset({"22", "23"})


class DataGoKrError(RuntimeError):
    """Base class for every operational error raised by pydatagokr."""


class DataGoKrConfigError(DataGoKrError):
    """The client is misconfigured; raised before any request goes out.

    The usual cause is a missing service key -- neither passed to the client nor present
    in the ``DATAGOKR_API_KEY`` environment variable nor the config file.
    """


class DataGoKrNetworkError(DataGoKrError):
    """The request failed at the transport or HTTP layer.

    A timeout, DNS failure, connection reset, an interrupted read, a non-success HTTP
    status, or a 200 whose body is not JSON (an XML fault, a proxy/maintenance page). The
    message carries the operation path but never the query string, and the cause chain is
    broken, so the key-bearing URL cannot ride along in a traceback.
    """


class DataGoKrPagingError(DataGoKrError):
    """Paging ran past the safety cap without a last-page signal.

    A guard against a vendor that never signals the end (its page count is wrong, or it
    keeps returning the same page): rather than return a result that looks complete but may
    be truncated, the session refuses it. Its own class -- not a
    :class:`DataGoKrNetworkError` -- so a bulk caller can tell "the data is suspect" apart
    from a transport failure it could simply retry.
    """


class DataGoKrResponseError(DataGoKrError):
    """data.go.kr rejected the call with an error code.

    When the failure came from an envelope, ``code`` and ``message`` are the vendor's own
    (``resultCode``/``resultMsg`` or ``returnReasonCode``/``errMsg``), so a caller can
    branch on the code without parsing the message text. The gateway can also reject a
    bad key with a bare HTTP 401/403 before any envelope exists (see
    :class:`DataGoKrAuthError`); there ``code`` is the HTTP status and ``message`` is
    synthesized by the package.
    """

    code: str
    message: str

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class DataGoKrAuthError(DataGoKrResponseError):
    """The portal rejected the service key (HTTP 401/403, or reason code 20, 30, or 31).

    Each data.go.kr dataset is applied for (활용신청) separately on the account; a call
    to one not yet approved fails exactly as a bad key does. It subclasses
    :class:`DataGoKrResponseError`, so ``except DataGoKrResponseError`` still catches it
    while a caller can catch an auth failure distinctly.
    """


class DataGoKrRateLimitError(DataGoKrResponseError):
    """The portal rejected the call volume (HTTP 429, or reason code 22/23).

    A :class:`DataGoKrResponseError` -- so ``except DataGoKrResponseError`` catches every
    coded rejection the portal reports, auth and rate-limit alike -- carrying the extra
    ``retry_after`` so a bulk caller can still catch it distinctly and back off rather than
    retry immediately. The vendor code is on ``.code`` (and the message on ``.message``), so a
    caller can tell 22 (daily traffic limit, resets at midnight KST) from 23 (per-second
    throttle); an HTTP-429 rejection that carries no envelope code uses ``"429"``.

    ``retry_after`` is the server's ``Retry-After`` delay in seconds when an HTTP 429 carried
    that header (its delta-seconds form), else ``None``; the caller decides whether to honor
    it. An envelope 22/23 rejection carries no such header, so ``retry_after`` is ``None``.
    """

    retry_after: int | None

    def __init__(self, code: str, message: str, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(code, message)


def _error_for(code: str, message: str) -> DataGoKrResponseError:
    """Build the most specific error for a data.go.kr envelope code.

    Serves both envelope shapes: the portal's ``returnReasonCode`` (error-B) and a
    service's ``resultCode`` (error-A) share the portal's common code vocabulary.

    Agencies zero-pad that code differently -- the standard is two digits (``"20"``) but
    some (국토부 RTMS) send three (``"020"``). Classification compares on the significant
    digits so a padded code lands in the same subclass; the raw code is preserved on the
    error's ``.code`` and in its message.
    """
    significant = code.lstrip("0") or "0"
    if significant in _AUTH_REASON_CODES:
        return DataGoKrAuthError(
            code, message or "data.go.kr rejected the service key or the dataset "
                             "is not applied for")
    if significant in _RATE_LIMIT_REASON_CODES:
        return DataGoKrRateLimitError(code, message or "traffic limit exceeded")
    return DataGoKrResponseError(code, message)
