"""The offline catalog -- every wrapped service and its operations, no key, no network.

Derived from the in-code registries: each service module exposes ``SERVICE``, ``AGENCY``,
``BASE_URL``, and a ``TABLES`` mapping, and this module reads those uniformly off the
:data:`_SERVICES` tuple. Adding a service to the catalog is adding its module to that
tuple -- nothing here enumerates operations by hand, so the catalog cannot drift from what
the client actually calls, and there is no bundled data file. (A new service is fully wired
only when it also has a :class:`~pydatagokr.client.DataGoKr` accessor and a CLI subcommand;
``tests/test_fleet.py`` fails if the catalog, the client accessors, and the CLI subcommands
drift apart.) :func:`services` names the
wrapped services, :func:`operations` lists the operation names each one's surface accepts
(through its ``fetch`` where it has one, else its typed methods -- ``airquality`` exposes
only ``by_sido``/``by_station``), and :func:`fields` gives one operation's clean column
schema.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from ._spec import FieldKind, Table, field_is_required
from .services import (
    airquality,
    customs,
    holidays,
    kofia,
    midforecast,
    procurement,
    realestate,
    weather,
)

__all__ = ["FieldSpec", "ServiceInfo", "fields", "operations", "services"]


class ServiceInfo(TypedDict):
    """One wrapped service's registry line: its accessor name, agency, and base URL."""

    service:  str
    agency:   str
    base_url: str


class FieldSpec(TypedDict):
    """One clean column's schema: the vendor token, the clean column, its kind, whether it is
    part of the natural key, and whether :func:`pydatagokr.clean` requires it (drops the row
    when it is missing). ``is_key`` marks the *natural* key; ``required`` is what actually
    governs nullability -- for a wide-key table a key column is **not** required, so a schema
    consumer must key on ``required``, not ``is_key``, to know a column can be ``None``."""

    token:    str
    column:   str
    kind:     FieldKind
    is_key:   bool
    required: bool


class _ServiceModule(Protocol):
    """The registry surface every service module exposes for the catalog to read."""

    SERVICE:  str
    AGENCY:   str
    BASE_URL: str
    TABLES:   dict[str, Table]


# The registry: one more service is one more module here, and every accessor picks it up.
# Ordered by the datasets' data.go.kr 활용신청 (application) counts, most-used first.
_SERVICES: tuple[_ServiceModule, ...] = (
    weather, airquality, holidays, realestate, midforecast, procurement, customs, kofia,
)


def services() -> list[ServiceInfo]:
    """The wrapped data.go.kr services, each as ``{service, agency, base_url}``."""
    return [ServiceInfo(service=module.SERVICE, agency=module.AGENCY,
                        base_url=module.BASE_URL) for module in _SERVICES]


def operations(service: str) -> list[str]:
    """The operation names one service's surface accepts, in declared order.

    Raises ``ValueError`` for an unknown service -- a caller mistake, the same signal
    ``KOFIA.fetch`` gives for an unknown operation.
    """
    return list(_module(service).TABLES)


def fields(service: str, operation: str) -> list[FieldSpec]:
    """One operation's clean column schema: a dict per field with its vendor ``token``,
    clean ``column``, ``kind``, ``is_key`` flag, and ``required`` flag (whether
    :func:`~pydatagokr.clean` drops a row when the field is missing -- the flag that
    actually governs nullability; see :class:`FieldSpec`), in table order.

        catalog.fields("kofia", "market_funds")   # -> [{"token": "basDt", ...}, ...]

    Reads the in-code table spec -- no network, no key. Raises ``ValueError`` for an
    unknown service or operation.

    Most ``token`` values are the vendor's own wire field; realestate's date token
    ``dealDate`` is the exception -- the surface synthesizes it from the vendor's
    dealYear/dealMonth/dealDay before cleaning, so it is not a field on a raw ``clean=False``
    row.
    """
    tables = _module(service).TABLES
    try:
        table = tables[operation]
    except KeyError:
        raise ValueError(f"unknown operation {operation!r} for service {service!r}; "
                         f"valid: {list(tables)}") from None
    return [FieldSpec(token=field.token, column=field.column, kind=field.kind,
                      is_key=field.is_key, required=field_is_required(field, table))
            for field in table.fields]


def _module(service: str) -> _ServiceModule:
    """The service module registered under ``service`` (raises ``ValueError`` if none)."""
    for module in _SERVICES:
        if service == module.SERVICE:
            return module
    raise ValueError(f"unknown service {service!r}; "
                     f"valid: {[module.SERVICE for module in _SERVICES]}")
