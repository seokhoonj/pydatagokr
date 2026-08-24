---
name: procurement
description: "Fetch 조달청 나라장터 입찰공고정보 (Korea Public Procurement Service bid announcements) from data.go.kr (service 1230000) -- one operation per 업무구분: `goods` (물품), `services` (용역), `construction` (공사), `foreign` (외자), over a 공고게시일시 time window. Holds no logic of its own -- it calls the pydatagokr package's CLI (`datagokr procurement`) and shows the result to the user. Trigger phrases: 나라장터, 입찰공고, 조달, 입찰, 공공조달, 물품 입찰, 용역 입찰, 공사 입찰, 관급공사, procurement, bid announcement, government tender, G2B."
---

# datagokr — 조달청 나라장터 입찰공고

Fetch 나라장터 bid announcements over a time window. The vendor requires the operation to
match the announcement's 업무구분, so there is one per kind. Clean columns (a curated header
subset of the vendor's ~100 fields): `notice_no`, `notice_ord`, `notice_name`,
`notice_kind`, `notice_agency` (공고기관), `demand_agency` (수요기관), `bid_method`,
`contract_method`, `notice_at`/`bid_close_at`/`opening_at` (times, text), `estimated_price`
(추정가격, 원 int), `budget_amount` (배정예산, 원 int), `officer_name`, `notice_url`,
`registered_at`.

| operation | 업무구분 |
|---|---|
| `goods` | 물품 |
| `services` | 용역 |
| `construction` | 공사 (배정예산 미제공 -- `budget_amount` is `None`) |
| `foreign` | 외자 |

## Prerequisite

```
pipx install pydatagokr      # or: pip install pydatagokr
```

**Never print the key value** (the `DATAGOKR_API_KEY` env var or `credentials.json`) to output, logs, or a summary -- if you need to check which form it is (encoding vs decoding), ask the user.

A data.go.kr **decoding** key must be configured (env `DATAGOKR_API_KEY` or
`~/.config/pydatagokr/credentials.json`), and the 나라장터 입찰공고정보서비스 dataset (service
1230000) applied for (활용신청). It is 자동승인 for a development account.

## Running

```
datagokr procurement <kind> --begin YYYYMMDDHHMM --end YYYYMMDDHHMM [--query-basis BASIS] [--json]
```

- `<kind>`: `goods` / `services` / `construction` / `foreign`.
- `--begin`/`--end`: the window as `YYYYMMDDHHMM` (e.g. `202608010000` .. `202608102359`).
- `--query-basis`: the window basis -- `1` 공고게시일시 (default), `2` 개찰일시.

## Procedure

1. **Pick the kind and window.** Match the 업무구분 to what the user wants (a 공사 search must
   use `construction`); keep the window modest (a few days) -- a large one returns many pages.
2. **Run.**
   ```bash
   datagokr procurement services --begin 202608010000 --end 202608102359
   ```
   Add `--json` for machine-readable data.
3. **Relay the result.** Report `notice_name`, the agencies, the 입찰마감·개찰 times, and the
   money (추정가격/배정예산 in 원); `notice_url` is the g2b.go.kr detail page.
4. **Error handling.** A one-line `datagokr: <message>` on stderr:
   - a `[30]`/`[20]` auth error -> the key is wrong, is the *encoding* form, or service
     1230000 is not applied for yet.
   - no rows means no announcements of that 업무구분 in the window (try another kind/window).

## What this skill does not do

- It does not re-implement fetching or parsing (the package does); it always calls the CLI.
- It returns the announcement *list* header, not the full 상세/기초금액/면허제한 sub-documents.
