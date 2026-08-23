# pydatagokr

[![check](https://github.com/seokhoonj/pydatagokr/actions/workflows/check.yml/badge.svg)](https://github.com/seokhoonj/pydatagokr/actions/workflows/check.yml)
[![PyPI](https://img.shields.io/pypi/v/pydatagokr)](https://pypi.org/project/pydatagokr/)
[![Python](https://img.shields.io/pypi/pyversions/pydatagokr)](https://pypi.org/project/pydatagokr/)
[![License](https://img.shields.io/pypi/l/pydatagokr)](https://github.com/seokhoonj/pydatagokr/blob/main/LICENSE)

**English** | [한국어](README.md)

Read the open APIs of Korea's public data portal ([data.go.kr](https://www.data.go.kr)). The
portal hosts thousands of agency APIs; the most-viewed and most-applied-for ones (weather, air
quality, holidays, real estate, mid-range forecasts, procurement, customs, and
financial-investment statistics) are pre-built here.

The pre-built services are called through an accessor, like `client.weather.forecast(...)`, and
any other service can be fetched directly once you know its request URL (see 2.2). The result
is a list of dicts (`list[dict]`), so `pandas.DataFrame(...)` turns it into a table right away.

## 1. Install

```bash
pip install pydatagokr
```

A data.go.kr API key is required. Use the **Decoding** key issued at
[data.go.kr](https://www.data.go.kr) -- not the Encoding key. Provide it in one of these ways.

**Option 1 — pass it directly** (for a quick one-off use)

```python
from pydatagokr import DataGoKr

client = DataGoKr(api_key="your-decoding-key")
```

**Option 2 — save it in a file** (recommended, so you only enter it once)

Create `~/.config/pydatagokr/credentials.json` with:

```json
{ "DATAGOKR_API_KEY": "your-decoding-key" }
```

After that, `DataGoKr()` finds the saved key automatically.

> If you prefer an environment variable, use `export DATAGOKR_API_KEY="your-decoding-key"` on
> macOS and Linux, or `setx DATAGOKR_API_KEY "your-decoding-key"` in Windows PowerShell.

The `datagokr` **CLI has no key argument**, so configure it through Option 2 (the file) or the
environment variable. The file path follows `$XDG_CONFIG_HOME` when set
(`$XDG_CONFIG_HOME/pydatagokr/credentials.json`), else `~/.config/pydatagokr/credentials.json`.

Each dataset must be applied for separately (활용신청) on your data.go.kr account before it can
be called. Click "활용신청" on the dataset's page, then check the approval status under My Page
> 데이터 활용 > Open API.

## 2. Quickstart

### 2.1 Listed services (current)

Call them directly through an accessor:

```python
from pydatagokr import DataGoKr

client = DataGoKr(api_key="your-decoding-key")   # or just DataGoKr() if you stored it

# Short-term forecast: Seoul Jongno grid (nx 60, ny 127). Omit base_date/base_time for the latest release
forecast = client.weather.forecast(nx=60, ny=127)

# Apartment sale transactions: Jongno-gu (11110), January 2024
trades = client.realestate.apt_trade(lawd_code="11110", deal_ym="202401")
```

### 2.2 Services that aren't pre-built

For data beyond the pre-built set, call it directly with `DataGoKrSession`. Open the dataset's
page on data.go.kr ([apartment sale
prices](https://www.data.go.kr/data/15126469/openapi.do)) and find these three:

| What to supply | Apartment sale prices |
|---|---|
| Request URL | `https://apis.data.go.kr/1613000` |
| Operation name | `RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade` |
| Request params (filters) | `LAWD_CD` (first 5 digits of the legal-dong code), `DEAL_YMD` (deal year-month) |

`DataGoKrSession` handles the key, paging across multiple pages, and errors, and returns the
agency's original field names as-is:

```python
from pydatagokr import DataGoKrSession

# For an XML service, set response_format="xml" (most are XML)
session = DataGoKrSession("https://apis.data.go.kr/1613000", response_format="xml")
rows = session.fetch(
    "RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",  # operation name
    LAWD_CD="11110",                               # first 5 digits of the legal-dong code
    DEAL_YMD="202401",                             # deal year-month (YYYYMM)
)
```

Either way the result is a `list[dict]`, so it goes straight into a pandas or polars table:

```python
# pandas
import pandas as pd
pd.DataFrame(rows)

# polars
import polars as pl
pl.DataFrame(rows)
```

## 3. List of pre-built services (current)

Services **pre-built** so you can use them right away among the portal's many APIs. Each
accessor has its own doc covering its operations, CLI/Python examples, and how to find the
codes it needs.

| Accessor | Agency · statistics | Format | Docs |
|---|---|---|---|
| `client.weather` | KMA village forecast (short-term, ultra-short-term, nowcast) | XML | [docs/weather.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/weather.md) |
| `client.airquality` | Korea Environment Corp. AirKorea air-pollution data | XML | [docs/airquality.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/airquality.md) |
| `client.holidays` | KASI special-day info (public holidays, 24 solar terms, etc.) | XML | [docs/holidays.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/holidays.md) |
| `client.realestate` | MOLIT apartment transaction prices (sale, rent, presale) | XML | [docs/realestate.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/realestate.md) |
| `client.midforecast` | KMA mid-range forecast (days 4-10: land, temperature) | XML | [docs/midforecast.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/midforecast.md) |
| `client.procurement` | PPS Nara-marketplace bid notices (goods, services, construction, foreign) | XML | [docs/procurement.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/procurement.md) |
| `client.customs` | KCS import/export by item (monthly, by HS code) | XML | [docs/customs.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/customs.md) |
| `client.kofia` | KOFIA aggregate statistics (deposits, funds, ELS/DLS, etc.) | JSON | [docs/kofia.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/kofia.md) |

> The linked per-service docs and `docs/errors.md` are currently written in Korean.

- **Apply first.** Each service must be applied for separately (활용신청) on your data.go.kr
  account before it can be called.
- **Readable names and real types (`clean`).** The agency's rows are hard to read by field name
  alone (`sggCd`, `excluUseAr`) and every value is a string. By default `clean=True` **renames
  fields to readable names and parses string values into real types** (`lawd_code`,
  `exclusive_area=84.97`, `deal_amount_manwon=82000`); an unparsable value becomes `None`. A row
  missing its date is dropped, and a composite-key table also drops a row missing a key dimension,
  but a wide-key table keeps the row with that value as `None`. `clean=False` leaves the agency's
  raw rows as they are.
- **Amount units are in the column name.** Apartment prices are in **10,000 KRW (만원)**
  (`deal_amount_manwon`, `deposit_manwon`, `monthly_rent_manwon`); procurement is in **KRW**
  (`estimated_price_krw`, `budget_amount_krw`); customs `export_usd` etc. are in **USD**. Still
  match units when summing amounts from several services in one table.
- **Discovery.** `datagokr list` shows the services and operations. In Python, `catalog.services()`
  lists the services, `catalog.operations("weather")` a service's operations, and
  `catalog.fields("weather", "forecast")` (CLI: `datagokr fields`) its tidied column schema.
  `datagokr <service> <operation> --help` shows each operation's options.
- **Errors & operations.** Reason codes, how approval works, and traffic limits are in
  [docs/errors.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/errors.md).

## 4. Command line

```bash
datagokr --version                                    # print the version
datagokr list                                         # services & operations (offline, no key)
datagokr fields weather forecast                      # one operation's tidied column schema (offline)
datagokr holidays --year 2026                         # public holidays
datagokr realestate apt_trade 11110 --deal-ym 202401  # apartment sale transactions

# Find codes (offline, no key) -- turn a lat/lon or place name into the code a service takes
datagokr grid 37.5714 126.9658                        # lat/lon -> KMA grid nx ny (60 127)
datagokr lawd 종로구                                   # place name -> 법정동코드 LAWD_CD (11110)
datagokr land-region 서울                              # place name -> mid-forecast land REGID (11B00000)
datagokr temp-region 서울                              # place name -> mid-forecast temp REGID (11B10101)
```

The call form is `datagokr <service> <operation> [options]`. The default output is a readable
summary; add `--json` for the full result as JSON. For each service's full commands and options,
and how to find codes, see the docs linked in the table above.

## 5. AI coding agents

This repository doubles as a plugin marketplace for Claude Code and Codex. `list`, `weather`,
`airquality`, `holidays`, `realestate`, `midforecast`, `procurement`, `customs`, and `kofia` are
provided as skills that call the same-named `datagokr` command. Install the package first
(above; `list` needs no key, fetches do).

### 5.1 Claude Code

In the Claude Code chat, add the marketplace and install:

```
/plugin marketplace add seokhoonj/pydatagokr   # add the marketplace
/plugin install datagokr@pydatagokr            # install the plugin
```

Then just ask ("show Seoul's fine dust", "Jongno-gu apartment sale transactions"), or call a
skill directly: `/datagokr:realestate apt_trade 11110 --deal-ym 202401`.

### 5.2 Codex

In the terminal, add the marketplace and install:

```
codex plugin marketplace add seokhoonj/pydatagokr   # add the marketplace
codex plugin add datagokr@pydatagokr                # install the plugin
```

The skills react to relevant requests, and you can also run `datagokr <service> <operation>`
directly.

### 5.3 Without a plugin (symlink)

To use them without installing a plugin, symlink a skill into your skills directory and call it
without the prefix (`datagokr:`), like `/weather`:

```sh
ln -s "$PWD/plugins/datagokr/skills/weather" ~/.claude/skills/weather   # Claude Code → /weather
ln -s "$PWD/plugins/datagokr/skills/weather" ~/.codex/skills/weather    # Codex → $weather
```

Claude Code picks it up immediately; Codex needs a restart to load it.

## 6. License

**The package code** is MIT (see `LICENSE`).

**The data** belongs to the providing agencies. Under Article 3 of the Public Data Act, public
data is in principle permitted for commercial use, but a specific dataset may restrict it or an
agency may suspend provision (Article 28). Check a dataset's terms of use before redistributing
its data.
