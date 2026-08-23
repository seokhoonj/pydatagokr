---
name: realestate
description: "Fetch 국토교통부 아파트 실거래가 (apartment real-transaction prices) from data.go.kr (MOLIT RTMS, service 1613000) -- sale (`apt_trade`), sale with road address (`apt_trade_detail`), rent/전월세 (`apt_rent`), and presale-right resale/분양권전매 (`apt_presale`), by 법정동 and 계약년월. Holds no logic of its own -- it calls the pydatagokr package's CLI (`datagokr realestate`) and shows the result to the user. Trigger phrases: 아파트 실거래가, 아파트 매매가, 전월세 실거래, 분양권 전매, 국토부 실거래가, 아파트 가격 조회, apartment transaction price, real estate deals."
---

# datagokr — 국토교통부 아파트 실거래가

Fetch a 시군구's apartment transactions for one 계약년월. Clean columns include `deal_date`,
`apt_name`, `exclusive_area` (m²), `floor`, `lawd_code`, `dong`, `jibun`, `build_year` --
and, by operation: `deal_amount_manwon` (거래금액, **만원**) for sale/presale, or
`deposit_manwon`/`monthly_rent_manwon` (보증금·월세, **만원**) for rent.

| operation | 데이터 |
|---|---|
| `apt_trade` | 아파트 매매 |
| `apt_trade_detail` | 아파트 매매 + 도로명주소 |
| `apt_rent` | 아파트 전월세 (보증금·월세) |
| `apt_presale` | 아파트 분양권전매 |

## Prerequisite

```
pipx install pydatagokr      # or: pip install pydatagokr
```

**Never print the key value** (the `DATAGOKR_API_KEY` env var or `credentials.json`) to output, logs, or a summary -- if you need to check which form it is (encoding vs decoding), ask the user.

A data.go.kr **decoding** key must be configured (env `DATAGOKR_API_KEY` or
`~/.config/pydatagokr/credentials.json`), and each apartment dataset (service 1613000)
applied for (활용신청) on that account -- the four are separate 활용신청.

## Running

```
datagokr realestate <operation> <LAWD_CD> --deal-ym YYYYMM [--json]
```

- `<operation>`: `apt_trade` / `apt_trade_detail` / `apt_rent` / `apt_presale`.
- `<LAWD_CD>`: the **5-digit 법정동 시군구코드** (예 종로구 `11110`, 강남구 `11680`) --
  the front 5 digits of the 행정표준코드 법정동 code.
- `--deal-ym`: 계약년월, `YYYYMM`.

## Procedure

1. **Resolve the region code.** Turn the 시군구 name into its LAWD_CD with the offline
   resolver -- `datagokr lawd 종로구` -> `11110` (add a 시도 when the name is ambiguous, e.g.
   `datagokr lawd "서울 중구"` -> `11140`). Take the 계약년월.
2. **Pick the operation.** 매매 -> `apt_trade`; 전월세 -> `apt_rent`; 분양권 -> `apt_presale`;
   need the road address -> `apt_trade_detail`.
3. **Run.**
   ```bash
   datagokr realestate apt_trade 11110 --deal-ym 202401
   ```
   Add `--json` for machine-readable data.
4. **Relay the result.** Show the CLI's stdout. Note amounts are in **만원** (거래금액·보증금·
   월세), and `exclusive_area` is m².
5. **Error handling.** A one-line `datagokr: <message>` on stderr:
   - a `[30]`/`[20]` auth error -> the key is wrong, is the *encoding* form by mistake,
     or that specific apartment dataset is not applied for yet.
   - a `[22]`/`[23]` rate limit -> wait and retry.

## What this skill does not do

- It does not re-implement fetching or parsing (the package does); it always calls the CLI.
- It resolves a 시군구 name to a LAWD_CD via `datagokr lawd`; it does not geocode a vague or
  free-form location.
