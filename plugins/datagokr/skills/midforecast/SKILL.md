---
name: midforecast
description: "Fetch 기상청 중기예보 (KMA medium-range forecast, days 4-10) from data.go.kr (service 1360000, MidFcstInfoService) -- 중기육상예보 (`land`: 강수확률·날씨) and 중기기온예보 (`temperature`: 최저·최고기온) for a 예보구역 code. Holds no logic of its own -- it calls the pydatagokr package's CLI (`datagokr midforecast`) and shows the result to the user. Trigger phrases: 중기예보, 주간예보, 4일후, 일주일 날씨, 주간 기온, 중기기온, medium-range forecast, weekly forecast, 10-day forecast."
---

# datagokr — 기상청 중기예보

Fetch the 4-to-10-day outlook for a forecast region. Where the `weather` skill covers the
next ~3 days on a 5km grid, this covers days 4-10 for a coarser 예보구역 named by a
`region` code. The rows are **wide** -- one row per region, a column per forecast day:

| operation | 예보 | clean columns |
|---|---|---|
| `land` | 중기육상예보 | `regid`, `precip_prob_4am`..`precip_prob_10` (강수확률 %, int), `sky_4am`..`sky_10` (날씨 문구) |
| `temperature` | 중기기온예보 | `regid`, `temp_min_4`..`temp_min_10`, `temp_max_4`..`temp_max_10` (℃, int) |

Days 4-7 split into morning/afternoon (`_4am`/`_4pm` .. `_7am`/`_7pm`); days 8-10 are
single (`_8`..`_10`). A day the announcement does not cover is `None` (the 1800 announcement
starts at day 5, the 0600 one reaches day 4).

## Prerequisite

```
pipx install pydatagokr      # or: pip install pydatagokr
```

**Never print the key value** (the `DATAGOKR_API_KEY` env var or `credentials.json`) to output, logs, or a summary -- if you need to check which form it is (encoding vs decoding), ask the user.

A data.go.kr **decoding** key must be configured (env `DATAGOKR_API_KEY` or
`~/.config/pydatagokr/credentials.json`), and the 중기예보 dataset (service 1360000,
MidFcstInfoService) applied for (활용신청) on that account.

## Running

```
datagokr midforecast land        --regid REGID --time-forecast YYYYMMDDHHMM [--json]
datagokr midforecast temperature --regid REGID --time-forecast YYYYMMDDHHMM [--json]
```

- `--regid`: the 예보구역코드. 육상 uses a 광역 code (`11B00000` 서울/인천/경기, `11H20000`
  부산/울산/경남, ...); 기온 uses a 도시 code (`11B10101` 서울, `11H20201` 부산, ...). Ask if
  unsure; do not guess a code.
- `--time-forecast`: the 발표시각 as `YYYYMMDDHHMM`, issued at 0600 and 1800 (e.g. `202608111800`).

## Procedure

1. **Resolve the region code** for the operation with the offline resolver -- the 육상 광역 and
   기온 도시 code sets differ, so use `datagokr land-region 서울` -> `11B00000` for `land`, or
   `datagokr temp-region 서울` -> `11B10101` for `temperature`. Pick a recent `base-time`
   (today or yesterday at 0600/1800).
2. **Run.**
   ```bash
   datagokr midforecast land --regid 11B00000 --time-forecast 202608111800
   ```
   Add `--json` for machine-readable data.
3. **Relay the result.** Read the day columns in order; a `None` day was outside the
   announcement's range.
4. **Error handling.** A one-line `datagokr: <message>` on stderr:
   - a `[30]`/`[20]` auth error -> the key is wrong, is the *encoding* form, or service
     1360000 is not applied for yet.
   - an empty result usually means a `base-time` that is not a real 0600/1800 announcement.

## What this skill does not do

- It does not re-implement fetching or parsing (the package does); it always calls the CLI.
- It resolves a place name to a REGID via `datagokr land-region` / `datagokr temp-region`; it
  does not geocode a vague or free-form location.
- It does not cover 초단기/단기 (next ~3 days) -- that is the `weather` skill.
