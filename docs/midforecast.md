# midforecast — 기상청 중기예보

기상청 중기예보 (서비스 `1360000` `MidFcstInfoService`, XML). 4~10일 예보를 예보구역
(`REGID`)별로 조회합니다. 단기예보(`weather`)가 5km 격자라면, 중기예보는 더 넓은
예보구역 단위입니다.

## 오퍼레이션

| 오퍼레이션 | 설명 | 구역코드 |
|---|---|---|
| `land` | 중기육상 (강수확률·하늘상태) | 광역 구역 (예 `11B00000` 서울·인천·경기) |
| `temperature` | 중기기온 (최저·최고) | 도시 코드 (예 `11B10101` 서울) |

`land`와 `temperature`는 서로 다른 구역코드 체계를 씁니다.

## CLI

```bash
datagokr midforecast land --regid 11B00000 --time-forecast 202608110600
datagokr midforecast temperature --regid 11B10101 --time-forecast 202608110600
```

`--time-forecast`은 발표시각(매일 `0600`·`1800`, YYYYMMDDHHMM). 0600 발표는 4일째까지,
1800 발표는 5일째부터 담습니다.

## Python

```python
from pydatagokr import DataGoKr, land_region, temp_region

client = DataGoKr()
land = client.midforecast.land(regid=land_region("서울"), time_forecast="202608110600")
temp = client.midforecast.temperature(regid=temp_region("서울"), time_forecast="202608110600")
```

## 예보구역코드 찾기

```bash
datagokr land-region 서울    # -> 11B00000  (중기육상 광역구역)
datagokr temp-region 서울    # -> 11B10101  (중기기온 도시)
```

Python은 `land_region(query) -> str`, `temp_region(query) -> str`.
