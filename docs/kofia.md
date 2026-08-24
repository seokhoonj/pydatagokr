# kofia — 금융투자협회 종합통계

금융투자협회 종합통계 (서비스 `1160100`, JSON). 투자자예탁금·신용공여잔고·펀드·CMA·
ELS/DLS·신탁·해외파생 등 시장 통계를 기간으로 조회합니다.

## 오퍼레이션

| 오퍼레이션 | 설명 |
|---|---|
| `market_funds` | 투자자예탁금 |
| `credit_balance` | 신용공여잔고 |
| `trust_scale` | 신탁 규모 |
| `fund_net_asset` | 펀드 순자산 |
| `cma_status` | CMA 잔고 |
| `dls_dlb` | DLS/DLB |
| `els_elb` | ELS/ELB |
| `overseas_derivatives` | 해외파생 |

## CLI

```bash
datagokr kofia market_funds --begin 20240101 --end 20240131
```

`--begin`/`--end`는 조회 구간입니다(YYYYMMDD; 월간 통계는 YYYYMM).

## Python

```python
from pydatagokr import DataGoKr

client = DataGoKr()
예탁금 = client.kofia.market_funds(begin="20240101", end="20240131")
els   = client.kofia.fetch("els_elb", begin="202401", end="202406")   # 월간 = YYYYMM
```

`market_funds`와 `credit_balance`는 편의 메서드로, 나머지 오퍼레이션은 `fetch(name, ...)`로
조회합니다. 전체 목록은 `datagokr list` / `KOFIA.operations()`.

금액 컬럼은 **원**입니다(`amount`·`account_balance`·신용/자금 잔고 등). 유일한 예외는
해외파생상품(`overseas_derivatives`)의 거래대금으로, 기관 토큰 `trPrcUsd`가 USD를 명시하므로
컬럼명이 `trade_value_usd`이며 단위는 **USD**입니다.
