"""Table specs -- vendor token -> clean column + type -- and the typed row cleaner.

The package's anti-corruption layer: a data.go.kr field vocabulary (``invrDpsgAmt``,
``crdTrFingWhl``, ...) is translated to clean snake_case column names in ONE place, next
to the service surface that speaks it, so a consumer never re-authors the mapping (or the
number parsing, or the vendor date-filter names). Each :class:`Table` is the single
source of truth a store can derive its schema and upsert from.

Two key shapes: a daily flow series is keyed by the date alone; a category-dimensioned
series keys on the date *and* its dimensions. :func:`clean` turns raw rows into
clean-named rows: 원화·건수는 exact int (bigint-safe -- float loses integers above 2^53),
비율은 float, 차원은 text, ``basDt`` (YYYYMMDD) / ``basYm`` (YYYYMM) as ISO date strings.
A row is dropped if its date is missing, or -- for a composite-key table -- any key
dimension is missing (a NULL cannot sit in a primary key). A wide-key table keeps such a
row with the dimension ``None``: its surrogate id needs no key, and the row's measures
are worth keeping.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from .types import Row

__all__ = ["CleanRow", "CleanValue", "Field", "FieldKind", "Table", "clean", "field_is_required"]

FieldKind = Literal["date_ymd", "date_ym", "text", "int", "ratio", "decimal"]
CleanValue = str | int | float | None
CleanRow = dict[str, CleanValue]


@dataclass(frozen=True, slots=True)
class Field:
    """One response field: the API token, the clean column, its type, and whether it is
    part of the natural key."""

    token:  str
    column: str
    kind:   FieldKind
    is_key: bool = False


@dataclass(frozen=True, slots=True)
class Table:
    """One operation's clean table: its name, the vendor operation path, its fields, and
    whether it uses no composite natural primary key -- because the key would be too wide, or
    the rows are wide/product-level -- so a store keys on a surrogate id + per-period replace.
    Under that flag :func:`clean` keeps a row whose key dimension is missing (as ``None``)
    rather than dropping it, since the surrogate id, not the key, identifies the row."""

    name:        str
    operation:   str
    fields:      tuple[Field, ...]
    is_wide_key: bool = False   # True -> surrogate id + per-period replace, not a composite PK

    def __post_init__(self) -> None:
        # Catch a copy-paste maintainer error at import time: a duplicate clean column would
        # be silently overwritten by clean(), a duplicate vendor token double-maps one field.
        for label, names in (("clean column", self.columns),
                             ("vendor token", tuple(f.token for f in self.fields))):
            dup = next((n for n, count in Counter(names).items() if count > 1), None)
            if dup is not None:
                raise ValueError(f"Table {self.name!r} has a duplicate {label}: {dup!r}")

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(field.column for field in self.fields)

    @property
    def key_columns(self) -> tuple[str, ...]:
        return tuple(field.column for field in self.fields if field.is_key)

    @property
    def date_column(self) -> str | None:
        """The clean column of this table's *first* date field, or ``None`` for a wide-key
        table that carries no date field (its rows are keyed by a surrogate id, not a period).
        A table may have several date fields (weather carries both ``base_date`` and
        ``forecast_date``), all of which :func:`clean` treats as required; this returns the
        first for the common single-date case."""
        return next((field.column for field in self.fields
                     if field.kind.startswith("date")), None)


def field_is_required(field: Field, table: Table) -> bool:
    """Whether :func:`clean` drops a row when this field parses to ``None``. A date field is
    always required (a row with no date is dropped); a non-date key dimension is required only
    for a composite-key table -- a wide-key table keeps the row with that dimension ``None``,
    since its surrogate id, not the key, identifies it. The single source of this rule so the
    cleaner and the catalog schema (:func:`pydatagokr.catalog.fields`) cannot disagree."""
    return field.kind.startswith("date") or (field.is_key and not table.is_wide_key)


def clean(rows: Iterable[Row], table: Table) -> list[CleanRow]:
    """Raw vendor rows -> clean-named rows (``table.columns`` in order): dates parsed to
    ISO strings, dimensions as text, 원화·건수는 int, 비율은 float. A row is dropped if
    its date is missing, or -- for a composite-key table -- any key dimension is missing
    (a NULL cannot key it); a wide-key table keeps the row with that dimension ``None``.
    A pure function: no I/O, no third-party frames -- the result is a ``list[dict]`` that
    ``pandas.DataFrame`` / ``polars.DataFrame`` accept directly."""
    # Resolve each field's parser and required-ness once, not per row.
    plan = [
        (field.token, field.column, _PARSER_BY_KIND[field.kind], field_is_required(field, table))
        for field in table.fields
    ]
    cleaned: list[CleanRow] = []
    for row in rows:
        values: CleanRow = {}
        keep = True
        for token, column, parser, required in plan:
            value = parser(row.get(token))
            if value is None and required:
                keep = False
                break
            values[column] = value
        if keep:
            cleaned.append(values)
    return cleaned


def _date_ymd(raw: object) -> str | None:
    """An 8-digit YYYYMMDD to an ISO date string (``"2024-01-05"``); anything else -> None."""
    text = str(raw).strip()
    if len(text) != 8 or not (text.isascii() and text.isdigit()):
        return None
    try:
        parsed = datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None
    return parsed.isoformat()


def _date_ym(raw: object) -> str | None:
    """A YYYYMM year-month to an ISO string (``"2024-01"``). Non-digit separators are
    stripped first, so both ``"202601"`` and the customs dotted form ``"2026.01"`` parse;
    anything not yielding a valid 6-digit YYYYMM -> None."""
    text = "".join(ch for ch in str(raw) if ch.isascii() and ch.isdigit())
    if len(text) != 6:
        return None
    try:
        date(int(text[:4]), int(text[4:6]), 1)   # validates the month
    except ValueError:
        return None
    return f"{text[:4]}-{text[4:6]}"


def _text(raw: object) -> str | None:
    """A dimension value as text; blank or the missing-markers (``"None"``, ``"nan"``) ->
    None, symmetric with ``_integer``/``_ratio``, so a missing key dimension is truly
    absent rather than a literal marker string."""
    text = str(raw).strip()
    if not text or text in ("nan", "None"):
        return None
    return text


def _integer(raw: object) -> int | None:
    """An amount or count string to an exact int (blank/``"-"``/``"None"``/``"nan"`` -> None). The
    plain integer path is exact for any magnitude; a decimal-formatted value
    (``"1234.0"``) is accepted only if integral, and a genuinely fractional one
    (``"3.8"``) -- a contract breach, these are integer won/counts -- becomes None rather
    than a lossy round."""
    text = str(raw).replace(",", "").strip()
    if not text or text in ("-", "None", "nan"):
        return None
    if not text.isascii():
        # int() accepts non-ASCII decimal digits (Arabic-Indic, full-width); a won/count is
        # always ASCII, and accepting them would disagree with the date parsers -> None.
        return None
    try:
        return int(text)                       # exact for any size (the common path)
    except ValueError:
        pass
    # A decimal-formatted integer ('1234.0', or '9007199254740993.0' above 2^53): take the
    # whole part as an exact int when the fraction is all zeros. Doing it on the STRING keeps
    # it exact (float would round away integers above 2^53) and -- because scientific notation
    # like '1E999999999' has no '.' and falls through to float below -- avoids materializing a
    # billion-digit int from a malicious exponent.
    whole, dot, frac = text.partition(".")
    if dot and frac.strip("0") == "":
        try:
            return int(whole)
        except ValueError:
            pass
    # Anything else -- a genuine fraction ('3.8') or scientific/inf notation -- goes through
    # float, which overflows a huge exponent to inf (-> None) rather than expanding it.
    try:
        number = float(text)
    except ValueError:
        return None
    # A non-finite float ("NaN"/"inf"/"Infinity") is not an integer won/count -> None.
    return int(number) if math.isfinite(number) and number.is_integer() else None


def _ratio(raw: object) -> float | None:
    """A percent string to a float (blank/``"-"``/``"None"``/``"nan"``/non-finite -> None)."""
    text = str(raw).replace(",", "").strip()
    if not text or text in ("-", "None", "nan") or not text.isascii():
        # float() accepts non-ASCII decimal digits (Arabic-Indic, full-width); a real
        # ratio/measure is always ASCII, and rejecting them keeps this symmetric with
        # _integer and the date parsers rather than typing one vendor row two ways.
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    # A non-finite float ("NaN"/"inf"/"Infinity") is not a real ratio -> None.
    return value if math.isfinite(value) else None


def _decimal(raw: object) -> float | None:
    """A decimal measure (area, coordinate, ...) to a float; blank/``"-"``/``"None"``/``"nan"``/
    non-finite -> None. Same parsing as :func:`_ratio`, kept a distinct kind so the schema
    reads honestly -- 전용면적 is a measure, not a percentage."""
    return _ratio(raw)


_PARSER_BY_KIND: dict[FieldKind, Callable[[object], CleanValue]] = {
    "date_ymd": _date_ymd,
    "date_ym":  _date_ym,
    "int":      _integer,
    "ratio":    _ratio,
    "decimal":  _decimal,
    "text":     _text,
}
