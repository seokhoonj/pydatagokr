---
name: customs
description: "Fetch Korea Customs Service (관세청) monthly item trade for one HS code from data.go.kr -- exports, imports, and weight by year-month. Holds no logic of its own -- it calls the pydatagokr package's CLI (`datagokr customs item_trade`) and shows the result to the user. Trigger phrases: 수출입실적, 품목별 수출입, HS 코드 수출, 관세청 무역통계, customs trade, item trade, exports by HS code."
---

# datagokr — 관세청 수출입 무역통계

Fetch one HS code's monthly 수출입실적 over a YYYYMM range. Clean columns: `period`
(YYYY-MM), `hs_code`, `item_name`, `export_dollar`, `export_weight`, `import_dollar`,
`import_weight`, `trade_balance` (all integers; `export_dollar`/`import_dollar`/`trade_balance`
in USD, the weights in kg). `--json` returns the full typed rows.

## Prerequisite

```
pipx install pydatagokr      # or: pip install pydatagokr
```

**Never print the key value** (the `DATAGOKR_API_KEY` env var or `credentials.json`) to output, logs, or a summary -- if you need to check which form it is (encoding vs decoding), ask the user.

A data.go.kr **decoding** key must be configured (env `DATAGOKR_API_KEY` or
`~/.config/pydatagokr/credentials.json`), and the 수출입 무역통계 dataset (service
1220000) applied for (활용신청) on that account.

## Running

```
datagokr customs item_trade <HS> --start YYYYMM --end YYYYMM [--json]
```

## Procedure

1. **Get the HS code.** Take it from the user (e.g. semiconductors 8542, cars 8703);
   2-, 4-, 6-, or 10-digit prefixes narrow or widen the item.
2. **Run.**
   ```bash
   datagokr customs item_trade 8542 --start 202401 --end 202406
   ```
   Add `--json` when the user wants machine-readable data.
3. **Relay the result.** Show the CLI's stdout (the clean columns above).
4. **Error handling.** A one-line `datagokr: <message>` on stderr:
   - a `[30]`/`[20]` auth error -> the key is wrong, is the *encoding* form by mistake,
     or service 1220000 is not applied for yet.
   - a `[22]`/`[23]` rate limit -> the daily traffic limit; wait and retry.

## What this skill does not do

- It does not re-implement fetching or parsing (the package does); it always calls the CLI.
- KOFIA market statistics are the **kofia** skill's job.
