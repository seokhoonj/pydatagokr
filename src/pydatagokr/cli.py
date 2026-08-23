"""Command-line shell over ``DataGoKr``.

``list`` browses the in-code catalog offline (no key) and ``fields`` shows one operation's
clean column schema offline. The fetch commands -- one per wrapped service: ``weather``,
``airquality``, ``holidays``, ``realestate``, ``midforecast``, ``procurement``, ``customs``,
``kofia`` -- each take the same service and operation names the Python client uses.

    $ datagokr list                                                # offline
    $ datagokr fields weather forecast                             # offline
    $ datagokr weather forecast --nx 60 --ny 127                   # 최신 발표분
    $ datagokr airquality by_sido 서울
    $ datagokr midforecast land --regid 11B00000 --time-forecast 202608111800
    $ datagokr procurement services --begin 202608010000 --end 202608102359
    $ datagokr customs item_trade 8542 --start 202401 --end 202406
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from collections.abc import Callable, Mapping, Sequence

from . import __version__, catalog
from .errors import DataGoKrError
from .grid import latlon_to_grid
from .regions import land_region, lawd_code, temp_region
from .services.airquality import AirQuality
from .services.customs import Customs
from .services.holidays import Holidays
from .services.kofia import KOFIA
from .services.midforecast import MidForecast
from .services.procurement import Procurement
from .services.realestate import RealEstate
from .services.weather import Weather

_PROG = "datagokr"
_ERROR_PREFIX = f"{_PROG}: "

# How many rows the text view prints; the full result is always in --json.
_MAX_SHOWN_ROWS = 20


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv``, run one call, and return a process exit code.

    A failure -- a missing/rejected key, a vendor error, or a transport problem -- is
    printed as a one-line ``datagokr: <message>`` to stderr and returns 1. A usage error
    caught here (an unknown operation, a ``ValueError`` from the client) returns 2;
    argparse's own usage errors (a bad flag or subcommand) raise ``SystemExit(2)``.
    """
    # Print Korean (agency names, values) on any console: force UTF-8 so a non-UTF-8 stdout
    # -- a Windows cp949 console, an ascii-encoded pipe -- does not die with UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    args = _make_parser().parse_args(argv)
    run: Callable[[argparse.Namespace], int] = args.run
    try:
        return run(args)
    except DataGoKrError as err:
        print(f"{_ERROR_PREFIX}{err}", file=sys.stderr)
        return 1
    except ValueError as err:
        print(f"{_ERROR_PREFIX}{err}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # A downstream reader closed the pipe early (`datagokr ... | head`). Redirect stdout to
        # devnull so Python's shutdown flush does not re-raise, then exit conventionally.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
        return 1


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG, description="Read Korean government open data (data.go.kr) "
                                "from the command line.")
    parser.add_argument("--version", action="version", version=f"{_PROG} {__version__}")
    commands = parser.add_subparsers(required=True)

    # Offline discovery and code resolvers register first, then the key-gated fetches.
    list_cmd = commands.add_parser("list", help="list services and operations (offline)")
    list_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
    list_cmd.set_defaults(run=_run_list)

    fields_cmd = commands.add_parser(
        "fields", help="show one operation's clean column schema (offline)")
    fields_cmd.add_argument("service", help="service name, e.g. kofia (see `datagokr list`)")
    fields_cmd.add_argument("operation", help="operation name, e.g. market_funds")
    fields_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
    fields_cmd.set_defaults(run=_run_fields)

    # Offline code resolvers (no key), mirroring the Python helpers.
    grid_cmd = commands.add_parser("grid", help="lat/lon -> KMA grid nx/ny (offline)")
    grid_cmd.add_argument("lat", type=float, help="위도 (decimal degrees)")
    grid_cmd.add_argument("lon", type=float, help="경도 (decimal degrees)")
    grid_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
    grid_cmd.set_defaults(run=_run_grid)

    lawd_cmd = commands.add_parser("lawd", help="지역명 -> 법정동코드 LAWD_CD (offline)")
    lawd_cmd.add_argument("query", help="시군구명 (예 종로구, '서울 중구')")
    lawd_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
    lawd_cmd.set_defaults(run=_run_lawd)

    land_region_cmd = commands.add_parser("land-region",
                                          help="지역명 -> 중기육상예보 REGID (offline)")
    land_region_cmd.add_argument("query", help="구역명 (예 서울)")
    land_region_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
    land_region_cmd.set_defaults(run=_run_land_region)

    temp_region_cmd = commands.add_parser("temp-region",
                                          help="지역명 -> 중기기온예보 REGID (offline)")
    temp_region_cmd.add_argument("query", help="도시명 (예 서울)")
    temp_region_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
    temp_region_cmd.set_defaults(run=_run_temp_region)

    kofia_cmd = commands.add_parser("kofia", help="fetch one KOFIA 종합통계 operation")
    kofia_cmd.add_argument("operation",
                           help="operation name, e.g. market_funds (see `datagokr list`)")
    kofia_cmd.add_argument("--begin", default=None, metavar="YYYYMMDD",
                           help="range start (YYYYMM for monthly operations)")
    kofia_cmd.add_argument("--end", default=None, metavar="YYYYMMDD",
                           help="range end (YYYYMM for monthly operations)")
    kofia_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
    kofia_cmd.set_defaults(run=_run_kofia)

    customs_cmd = commands.add_parser("customs", help="관세청 수출입 무역통계")
    customs_ops = customs_cmd.add_subparsers(required=True)
    item_trade_cmd = customs_ops.add_parser(
        "item_trade", help="fetch one HS code's monthly 수출입실적")
    item_trade_cmd.add_argument("hs_code", metavar="HS", help="HS code (hsSgn)")
    item_trade_cmd.add_argument("--start", required=True, metavar="YYYYMM",
                                help="range start")
    item_trade_cmd.add_argument("--end", required=True, metavar="YYYYMM",
                                help="range end")
    item_trade_cmd.add_argument("--json", action="store_true",
                                help="emit JSON instead of text")
    item_trade_cmd.set_defaults(run=_run_customs_item_trade)

    holidays_cmd = commands.add_parser("holidays", help="한국천문연구원 특일 정보")
    holidays_cmd.add_argument("operation", nargs="?", default="holidays",
                              help="holidays (default) / national_holidays / anniversaries "
                                   "/ solar_terms / sundry_days")
    holidays_cmd.add_argument("--year", required=True, type=int, metavar="YYYY",
                              help="solar year")
    holidays_cmd.add_argument("--month", default=None, type=int, metavar="M",
                              help="1-12 (optional; omit for the whole year)")
    holidays_cmd.add_argument("--json", action="store_true",
                              help="emit JSON instead of text")
    holidays_cmd.set_defaults(run=_run_holidays)

    realestate_cmd = commands.add_parser("realestate", help="국토교통부 아파트 실거래가")
    re_ops = realestate_cmd.add_subparsers(required=True)
    for op, desc in (("apt_trade", "아파트 매매"), ("apt_trade_detail", "아파트 매매 상세"),
                     ("apt_rent", "아파트 전월세"), ("apt_presale", "아파트 분양권전매")):
        op_cmd = re_ops.add_parser(op, help=f"fetch {desc} 실거래가")
        op_cmd.add_argument("lawd_code", metavar="LAWD_CD",
                            help="법정동 앞5자리 (예 종로구 11110)")
        op_cmd.add_argument("--deal-ym", required=True, metavar="YYYYMM", dest="deal_ym",
                            help="계약년월")
        op_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
        op_cmd.set_defaults(run=_run_realestate, operation=op)

    weather_cmd = commands.add_parser("weather", help="기상청 동네예보")
    weather_ops = weather_cmd.add_subparsers(required=True)
    for op, desc in (("forecast", "단기예보"), ("ultra_forecast", "초단기예보"),
                     ("nowcast", "초단기실황")):
        op_cmd = weather_ops.add_parser(op, help=f"fetch {desc}")
        op_cmd.add_argument("--base-date", default=None, metavar="YYYYMMDD", dest="base_date",
                            help="발표일자 (--base-time과 함께; 둘 다 생략 시 최신 발표분)")
        op_cmd.add_argument("--base-time", default=None, metavar="HHMM", dest="base_time",
                            help="발표시각 (--base-date와 함께; 둘 다 생략 시 최신 발표분)")
        op_cmd.add_argument("--nx", required=True, type=int, help="격자 X")
        op_cmd.add_argument("--ny", required=True, type=int, help="격자 Y")
        op_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
        op_cmd.set_defaults(run=_run_weather, operation=op)

    aq_cmd = commands.add_parser("airquality", help="한국환경공단 에어코리아 대기오염정보")
    aq_ops = aq_cmd.add_subparsers(required=True)
    sido_cmd = aq_ops.add_parser("by_sido", help="fetch 시도별 실시간 측정")
    sido_cmd.add_argument("sido", help="시도명 (서울/부산/경기 ...)")
    sido_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
    sido_cmd.set_defaults(run=_run_airquality_by_sido)
    station_cmd = aq_ops.add_parser("by_station", help="fetch 측정소별 실시간 측정")
    station_cmd.add_argument("station", help="측정소명 (예 종로구)")
    station_cmd.add_argument("--data-term", default=argparse.SUPPRESS, dest="data_term",
                             choices=("DAILY", "MONTH", "3MONTH"), metavar="TERM",
                             help="DAILY (default) / MONTH / 3MONTH")
    station_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
    station_cmd.set_defaults(run=_run_airquality_by_station)

    mid_cmd = commands.add_parser("midforecast", help="기상청 중기예보")
    mid_ops = mid_cmd.add_subparsers(required=True)
    for op, desc in (("land", "중기육상예보"), ("temperature", "중기기온예보")):
        op_cmd = mid_ops.add_parser(op, help=f"fetch {desc}")
        op_cmd.add_argument("--regid", required=True, metavar="REGID",
                            help="예보구역코드 (예 11B00000)")
        op_cmd.add_argument("--time-forecast", required=True, metavar="YYYYMMDDHHMM",
                            dest="time_forecast", help="발표시각 (0600/1800)")
        op_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
        op_cmd.set_defaults(run=_run_midforecast, operation=op)

    proc_cmd = commands.add_parser("procurement", help="조달청 나라장터 입찰공고")
    proc_ops = proc_cmd.add_subparsers(required=True)
    for op, desc in (("goods", "물품"), ("services", "용역"),
                     ("construction", "공사"), ("foreign", "외자")):
        op_cmd = proc_ops.add_parser(op, help=f"fetch {desc} 입찰공고")
        op_cmd.add_argument("--begin", required=True, metavar="YYYYMMDDHHMM",
                            help="공고게시 시작")
        op_cmd.add_argument("--end", required=True, metavar="YYYYMMDDHHMM",
                            help="공고게시 종료")
        op_cmd.add_argument("--query-basis", default=argparse.SUPPRESS, dest="query_basis",
                            choices=("1", "2"), metavar="BASIS",
                            help="조회 기준 (1 공고게시일시[기본] / 2 개찰일시)")
        op_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")
        op_cmd.set_defaults(run=_run_procurement, operation=op)

    return parser


def _run_list(args: argparse.Namespace) -> int:
    listed = catalog.services()
    if args.json:
        print(json.dumps(
            {entry["service"]: catalog.operations(entry["service"]) for entry in listed},
            ensure_ascii=False, indent=2))
        return 0
    lines = []
    for entry in listed:
        lines.append(f"{entry['service']} -- {entry['agency']}")
        lines += [f"  {entry['service']} {name}"
                  for name in catalog.operations(entry["service"])]
    print("\n".join(lines))
    return 0


def _run_fields(args: argparse.Namespace) -> int:
    # catalog.fields raises ValueError for an unknown service/operation, which main()
    # turns into a usage error (exit 2) with the message it built.
    _emit(catalog.fields(args.service, args.operation), args.json)
    return 0


def _run_grid(args: argparse.Namespace) -> int:
    grid = latlon_to_grid(args.lat, args.lon)
    print(json.dumps({"nx": grid.nx, "ny": grid.ny}) if args.json else f"{grid.nx} {grid.ny}")
    return 0


def _run_lawd(args: argparse.Namespace) -> int:
    # A no/ambiguous match raises ValueError -> main() prints it and returns 2.
    code = lawd_code(args.query)
    print(json.dumps({"code": code}, ensure_ascii=False) if args.json else code)
    return 0


def _run_land_region(args: argparse.Namespace) -> int:
    code = land_region(args.query)
    print(json.dumps({"code": code}, ensure_ascii=False) if args.json else code)
    return 0


def _run_temp_region(args: argparse.Namespace) -> int:
    code = temp_region(args.query)
    print(json.dumps({"code": code}, ensure_ascii=False) if args.json else code)
    return 0


def _run_kofia(args: argparse.Namespace) -> int:
    # Validated before KOFIA(), so a misused command is a usage error (exit 2)
    # without needing a service key.
    if args.operation not in catalog.operations("kofia"):
        print(f"{_ERROR_PREFIX}unknown operation {args.operation!r} "
              f"(try `{_PROG} list`)", file=sys.stderr)
        return 2
    rows = KOFIA().fetch(args.operation, begin=args.begin, end=args.end)
    _emit(rows, args.json)
    return 0


def _run_customs_item_trade(args: argparse.Namespace) -> int:
    rows = Customs().item_trade(args.hs_code, start=args.start, end=args.end)
    _emit(rows, args.json)
    return 0


def _run_holidays(args: argparse.Namespace) -> int:
    if args.operation not in catalog.operations("holidays"):
        print(f"{_ERROR_PREFIX}unknown operation {args.operation!r} "
              f"(try `{_PROG} list`)", file=sys.stderr)
        return 2
    rows = Holidays().fetch(args.operation, year=args.year, month=args.month)
    _emit(rows, args.json)
    return 0


def _run_realestate(args: argparse.Namespace) -> int:
    rows = RealEstate().fetch(args.operation, lawd_code=args.lawd_code,
                              deal_ym=args.deal_ym)
    _emit(rows, args.json)
    return 0


def _run_weather(args: argparse.Namespace) -> int:
    rows = Weather().fetch(args.operation, base_date=args.base_date,
                           base_time=args.base_time, nx=args.nx, ny=args.ny)
    _emit(rows, args.json)
    return 0


def _run_airquality_by_sido(args: argparse.Namespace) -> int:
    _emit(AirQuality().by_sido(sido=args.sido), args.json)
    return 0


def _run_airquality_by_station(args: argparse.Namespace) -> int:
    # --data-term is SUPPRESSed when unset, so forward it only when the user gave one and
    # let by_station choose the default otherwise (no restated default at the call site).
    air = AirQuality()
    if hasattr(args, "data_term"):
        rows = air.by_station(station=args.station, data_term=args.data_term)
    else:
        rows = air.by_station(station=args.station)
    _emit(rows, args.json)
    return 0


def _run_midforecast(args: argparse.Namespace) -> int:
    rows = MidForecast().fetch(args.operation, regid=args.regid,
                               time_forecast=args.time_forecast)
    _emit(rows, args.json)
    return 0


def _run_procurement(args: argparse.Namespace) -> int:
    # --query-basis is SUPPRESSed when unset, so forward it only when the user gave one and
    # let fetch choose the default otherwise (no restated default at the call site).
    pr = Procurement()
    if hasattr(args, "query_basis"):
        rows = pr.fetch(args.operation, begin=args.begin, end=args.end,
                        query_basis=args.query_basis)
    else:
        rows = pr.fetch(args.operation, begin=args.begin, end=args.end)
    _emit(rows, args.json)
    return 0


def _emit(rows: Sequence[Mapping[str, object]], as_json: bool) -> None:
    if as_json:
        print(json.dumps(list(rows), ensure_ascii=False, indent=2))
    else:
        print(_render_rows(rows))


def _render_rows(rows: Sequence[Mapping[str, object]]) -> str:
    """Rows as an aligned table over the first row's keys (up to ``_MAX_SHOWN_ROWS``),
    then a total count. Empty -> ``(no rows)``."""
    if not rows:
        return "(no rows)"
    headers = list(rows[0].keys())
    shown = rows[:_MAX_SHOWN_ROWS]
    body = [[_cell(row.get(key)) for key in headers] for row in shown]
    columns = list(zip(headers, *body, strict=True))
    widths = [max(_display_width(cell) for cell in column) for column in columns]
    head = "  ".join(_pad(h, w) for h, w in zip(headers, widths, strict=True))
    lines = ["  ".join(_pad(cell, w) for cell, w in zip(row, widths, strict=True))
             for row in body]
    table = "\n".join([head, *lines])
    if len(rows) > len(shown):
        return f"{table}\n... ({len(rows)} rows total, showing {len(shown)})"
    return f"{table}\n({len(rows)} rows)"


def _cell(value: object) -> str:
    if value is None:
        return ""
    # NFC so composed Hangul measures at its true width; collapse newlines/tabs to a space so
    # a multi-line vendor value cannot break the table's row/column structure.
    text = unicodedata.normalize("NFC", str(value))
    for control in "\r\n\t":
        text = text.replace(control, " ")
    return text


def _display_width(text: str) -> int:
    """Terminal cell width: East-Asian Wide/Fullwidth glyphs (Hangul, ...) take two
    cells, so padding by ``len`` misaligns a column of mixed Korean labels."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    """Left-justify ``text`` to ``width`` terminal cells (wide glyphs counted as two)."""
    return text + " " * max(0, width - _display_width(text))


if __name__ == "__main__":
    raise SystemExit(main())
