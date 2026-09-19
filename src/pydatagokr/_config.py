"""Resolve the data.go.kr service key from the caller, the environment, or the config file.

The key MUST be the data.go.kr **decoding** (raw) key. The portal issues every key in two
forms -- 인증키 (Encoding), a percent-escaped copy, and 인증키 (Decoding), the raw value --
and this package url-encodes query parameters exactly once, so the raw decoding key is
the one that authenticates; the pre-escaped encoding form gets double-encoded into a
rejected request.

The key is looked up in a fixed order, so an explicit value always wins and a set
environment variable beats a file on disk:

1. the ``api_key`` passed to ``DataGoKr(...)`` / a service surface / a session
2. the ``DATAGOKR_API_KEY`` environment variable
3. ``"DATAGOKR_API_KEY"`` in ``$XDG_CONFIG_HOME/pydatagokr/credentials.json``
   (``$XDG_CONFIG_HOME`` defaults to ``~/.config``)

The resolution, the whitespace trimming, the permission handling (a group/other-readable
file is warned about, not refused), and the storage backend are delegated to credbox. The
store binding is not hardcoded: ``Credentials.for_app("pydatagokr")`` lets a host embedding
pydatagokr redirect it via ``PYDATAGOKR_STORE_APP`` / ``PYDATAGOKR_NAMESPACE``; standalone
it is exactly the flat ``~/.config/pydatagokr/credentials.json`` pydatagokr has always read.
A file that is present but unreadable, not JSON, or not a JSON object is still an error
rather than a silent skip.

Once a key is found, it is still checked for characters it cannot put in a request URL
here -- credbox trims surrounding whitespace but keeps an embedded newline/tab, a non-ASCII
character, or a lone surrogate (from corrupt environment bytes), any of which can only be a
broken key and would make urllib echo the value while url-encoding it. That check is
pydatagokr's own concern, not something the credential store knows about.
"""

from __future__ import annotations

from functools import lru_cache

from credbox import CredBoxError, Credentials

from .errors import DataGoKrConfigError

_ENV_VAR = "DATAGOKR_API_KEY"
_STORE_APP = "pydatagokr"


def resolve_api_key(explicit: str | None) -> str:
    """Return the first key found across the three sources (explicit, env, file).

    Raises :class:`DataGoKrConfigError` when no source supplies a key, when the resolved key
    contains a character it cannot put in a request URL (a control character, a non-ASCII
    character, or a lone surrogate -- usually a broken paste or corrupt environment bytes),
    or when the credential store cannot be read or its binding is malformed (unreadable, not
    UTF-8, not JSON, not a JSON object, or an invalid ``PYDATAGOKR_STORE_APP`` /
    ``PYDATAGOKR_NAMESPACE``).
    """
    credentials = _get_credentials()
    try:
        found = credentials.secret(_ENV_VAR, override=explicit)
    except CredBoxError as err:
        # credbox's message already names the store path + fault; don't prepend a static
        # path (wrong under a PYDATAGOKR_STORE_APP redirect). credbox detaches
        # secret-bearing context, so chaining `from err` keeps the key out of any traceback.
        raise DataGoKrConfigError(f"could not read the credential store: {err}") from err
    if found is None:
        # Binding validated cleanly above (None, not error), so store_location() is safe
        # and gives the real store (the host's under a redirect).
        raise DataGoKrConfigError(
            f"no data.go.kr service key: pass api_key=, set the {_ENV_VAR} environment "
            f"variable, or put it in {credentials.store_location()} "
            f"-- use the *decoding* (raw) key"
        )
    key = found.reveal()
    if any(not (0x20 <= ord(ch) < 0x7F) for ch in key):
        # The key goes into the request URL, url-encoded. A byte outside printable ASCII
        # -- a stray newline/tab from a copy-paste, a non-ASCII character, or a lone
        # surrogate from corrupt environment bytes -- can only be a broken key, and would
        # make urllib raise *while encoding it*, echoing the value. Reject it here, before
        # it becomes a request, and never echo it. data.go.kr keys are ASCII, so no
        # legitimate key is lost.
        raise DataGoKrConfigError(
            "the data.go.kr service key contains a character it cannot put in a request "
            "URL (a stray newline, tab, or non-ASCII character?)")
    return key


@lru_cache(maxsize=1)
def _get_credentials() -> Credentials:
    """pydatagokr's credbox credential store, built on first use and cached.

    Built via ``for_app`` (not the bare ``Credentials(...)``) so a host embedding
    pydatagokr can redirect the binding with ``PYDATAGOKR_STORE_APP`` /
    ``PYDATAGOKR_NAMESPACE`` before the first lookup. credbox re-resolves the store *path*
    per call (honouring a later ``XDG_CONFIG_HOME``); the binding is read from the
    environment once, when this facade is built. A malformed binding surfaces as
    ``DataGoKrConfigError`` on the first lookup that actually reaches the store -- an
    explicit argument or ``DATAGOKR_API_KEY`` resolves first, so a bad binding with the env
    var set never raises.
    """
    return Credentials.for_app(_STORE_APP)
