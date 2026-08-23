# realestate — 국토교통부 아파트 실거래가

국토교통부 아파트 실거래가 (서비스 `1613000`, XML). 시군구(법정동코드 앞 5자리,
`LAWD_CD`) 단위로 한 계약년월의 거래를 조회합니다.

## 오퍼레이션

| 오퍼레이션 | 설명 |
|---|---|
| `apt_trade` | 매매 |
| `apt_trade_detail` | 매매 상세 |
| `apt_rent` | 전월세 |
| `apt_presale` | 분양권전매 |

## CLI

```bash
datagokr realestate apt_trade 11110 --deal-ym 202401
```

첫 인자는 `LAWD_CD`(법정동 앞 5자리), `--deal-ym`은 계약년월(YYYYMM)입니다.

금액 단위는 **만원**입니다 -- `deal_amount_manwon`(거래금액)·`deposit_manwon`(보증금)·
`monthly_rent_manwon`(월세)가 모두 만원(예: `deal_amount_manwon=82000`은 8.2억 원),
`exclusive_area`는 ㎡입니다. (컬럼명에 단위를 담아 원/USD 서비스와 섞어 더할 때 헷갈리지 않게 했습니다.)

## Python

```python
from pydatagokr import DataGoKr, lawd_code

client = DataGoKr()
code = lawd_code("종로구")                  # "11110"
rows = client.realestate.apt_trade(lawd_code=code, deal_ym="202401")
```

## 법정동코드 찾기

`LAWD_CD`는 법정동코드 앞 5자리입니다. 지역명으로 찾으세요:

```bash
datagokr lawd 종로구        # -> 11110
datagokr lawd "서울 중구"   # 이름이 여러 시도에 있으면 시도를 붙여 한정
datagokr lawd "수원시 장안구"
```

이름이 중복되면(예 `중구`) 후보 목록과 함께 실패하니 `"서울 중구"`처럼 시도를, 일반구는
`"수원시 장안구"`처럼 상위 시를 붙입니다. Python은 `lawd_code(query) -> str`.
