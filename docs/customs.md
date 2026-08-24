# customs — 관세청 품목별 수출입실적

관세청 품목별 수출입실적 (서비스 `1220000` `Itemtrade`, XML). 한 HS 부호의 월별
수출/수입 금액·중량을 조회합니다.

## 오퍼레이션

| 오퍼레이션 | 설명 |
|---|---|
| `item_trade` | HS 부호별 월 수출/수입 실적 |

## CLI

```bash
datagokr customs item_trade 8542 --start 202401 --end 202406
```

첫 인자는 HS 부호(`8542` = 반도체 집적회로), `--start`/`--end`는 조회 구간(YYYYMM).

## Python

```python
from pydatagokr import DataGoKr

client = DataGoKr()
rows = client.customs.item_trade("8542", start="202401", end="202406")
```

금액(`export_dollar`·`import_dollar`·`trade_balance`)은 **USD**, 중량(`export_weight`·
`import_weight`)은 **kg**입니다. 무역수지(`trade_balance`)는 수출액 - 수입액이며 음수일 수
있습니다. HS 부호는 관세청 HS 품목분류표에서 확인하세요.
