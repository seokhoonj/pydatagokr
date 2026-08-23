# pydatagokr

[![check](https://github.com/seokhoonj/pydatagokr/actions/workflows/check.yml/badge.svg)](https://github.com/seokhoonj/pydatagokr/actions/workflows/check.yml)
[![PyPI](https://img.shields.io/pypi/v/pydatagokr)](https://pypi.org/project/pydatagokr/)
[![Python](https://img.shields.io/pypi/pyversions/pydatagokr)](https://pypi.org/project/pydatagokr/)
[![License](https://img.shields.io/pypi/l/pydatagokr)](https://github.com/seokhoonj/pydatagokr/blob/main/LICENSE)

**한국어** | [English](README.en.md)

공공데이터포털([data.go.kr](https://www.data.go.kr))의 오픈 API를 읽어옵니다. 포털에는 수천 개
기관 API가 있고, 그중 조회수·활용신청이 높은 것들(기상·대기·공휴일·부동산·중기예보·조달·
관세·금융투자)을 미리 만들어 두었습니다.

미리 만든 서비스는 `client.weather.forecast(...)`처럼 접근자(accessor)로 부르고, 목록에
없는 서비스도 요청 주소만 알면 직접 가져올 수 있습니다(아래 2.2). 결과는 딕셔너리 목록
(`list[dict]`)이라 `pandas.DataFrame(...)`으로 바로 표가 됩니다.

## 1. 설치

```bash
pip install pydatagokr
```

data.go.kr 인증키가 필요합니다. [data.go.kr](https://www.data.go.kr)에서 발급받은
**Decoding(디코딩)** 키를 복사하세요(Encoding 키가 아닙니다). 키를 넣는 방법은 세 가지입니다.

**① 코드에서 직접**: `DataGoKr(api_key="발급받은-디코딩-키")` (아래 빠른 시작).

**② 파일에 저장**(권장, 한 번 넣으면 이후 `DataGoKr()`만 써도 됨). 아래를 `~/.config/pydatagokr/credentials.json`에 저장합니다:

```json
{ "DATAGOKR_API_KEY": "발급받은-디코딩-키" }
```

**③ 환경변수**: macOS·Linux는 `export DATAGOKR_API_KEY=발급받은-디코딩-키`, Windows
PowerShell은 `setx DATAGOKR_API_KEY "발급받은-디코딩-키"`.

①은 Python 전용입니다 -- `datagokr` **CLI에는 키 인자가 없으니** ②(파일) 또는 ③(환경변수)로
넣으세요. 파일 경로는 `$XDG_CONFIG_HOME`이 설정돼 있으면 그 아래
(`$XDG_CONFIG_HOME/pydatagokr/credentials.json`), 아니면 `~/.config/pydatagokr/credentials.json`
입니다.

데이터마다 data.go.kr에서 따로 **활용신청**(사용 신청)을 해야 불러올 수 있습니다. 그
데이터의 안내 페이지에서 "활용신청"을 누르고, 마이페이지 > 데이터 활용 > Open API에서
승인됐는지 봅니다.

## 2. 빠른 시작

### 2.1 지원 서비스 (현재 기준)

접근자로 바로 부릅니다:

```python
from pydatagokr import DataGoKr

client = DataGoKr(api_key="발급받은-디코딩-키")   # 저장해 뒀으면 DataGoKr()

# 단기예보: 서울 종로 격자(nx 60, ny 127). base_date/base_time 생략 시 최신 발표분
forecast = client.weather.forecast(nx=60, ny=127)

# 아파트 매매 실거래: 종로구(11110), 2024년 1월
trades = client.realestate.apt_trade(lawd_code="11110", deal_ym="202401")
```

### 2.2 목록에 없는 서비스

미리 만든 것 말고 다른 데이터가 필요하면 `DataGoKrSession`으로 직접 부릅니다. data.go.kr에서
그 데이터의 안내 페이지([아파트 매매
실거래가](https://www.data.go.kr/data/15126469/openapi.do))를 열고 아래 셋을 찾아 넣습니다:

| 넣을 것 | 아파트 매매 실거래가 |
|---|---|
| 요청 주소 | `https://apis.data.go.kr/1613000` |
| 기능명 (오퍼레이션) | `RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade` |
| 요청 항목 (필터) | `LAWD_CD`(법정동코드 앞 5자리), `DEAL_YMD`(계약년월) |

인증키 넣기, 여러 페이지로 나뉜 결과 이어받기, 오류 처리는 `DataGoKrSession`이 알아서 하고,
기관이 준 원래 항목 이름 그대로 돌려줍니다:

```python
from pydatagokr import DataGoKrSession

# XML로 답하는 서비스면 response_format="xml" (대부분 XML)
session = DataGoKrSession("https://apis.data.go.kr/1613000", response_format="xml")
rows = session.fetch(
    "RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",  # 기능명
    LAWD_CD="11110",                               # 법정동코드 앞 5자리
    DEAL_YMD="202401",                             # 계약년월(YYYYMM)
)
```

결과는 접근자로 부른 것과 똑같이 `list[dict]`이라 pandas·polars 표로 바로 만듭니다:

```python
# pandas
import pandas as pd
pd.DataFrame(rows)

# polars
import polars as pl
pl.DataFrame(rows)
```

## 3. 지원 서비스 (현재 기준)

포털의 수많은 API 중 지금 바로 쓰도록 **미리 만들어 둔** 서비스입니다. 접근자마다 상세
문서가 있어 오퍼레이션·CLI/Python 예시·필요한 코드를 찾는 법을 담았습니다.

| 접근자 | 기관 · 통계 | 포맷 | 문서 |
|---|---|---|---|
| `client.weather` | 기상청 동네예보 (단기·초단기·실황) | XML | [docs/weather.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/weather.md) |
| `client.airquality` | 한국환경공단 에어코리아 대기오염정보 | XML | [docs/airquality.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/airquality.md) |
| `client.holidays` | 한국천문연구원 특일 정보 (공휴일·24절기 등) | XML | [docs/holidays.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/holidays.md) |
| `client.realestate` | 국토교통부 아파트 실거래가 (매매·전월세·분양권) | XML | [docs/realestate.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/realestate.md) |
| `client.midforecast` | 기상청 중기예보 (4~10일 육상·기온) | XML | [docs/midforecast.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/midforecast.md) |
| `client.procurement` | 조달청 나라장터 입찰공고 (물품·용역·공사·외자) | XML | [docs/procurement.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/procurement.md) |
| `client.customs` | 관세청 품목별 수출입실적 (HS 부호별 월간) | XML | [docs/customs.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/customs.md) |
| `client.kofia` | 금융투자협회 종합통계 (예탁금·펀드·ELS/DLS 등) | JSON | [docs/kofia.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/kofia.md) |

- **활용신청이 먼저.** 서비스마다 data.go.kr 계정에서 해당 데이터셋을 따로 신청해야
  호출됩니다.
- **이름·타입 정리(`clean`).** 기관이 주는 행은 필드명만으로는 의미를 알기 어렵고(`sggCd`,
  `excluUseAr`) 값이 전부 문자열입니다. 기본값 `clean=True`는 **필드명을 알아보기 쉬운 이름으로
  바꾸고 문자열 값을 실제 타입으로 변환**하며(`lawd_code`, `exclusive_area=84.97`,
  `deal_amount_manwon=82000`), 파싱되지 않는 값은 `None`으로 둡니다. 날짜가 빠진 행은 결과에서 빼고,
  복합키 테이블은 키 차원이 빠진 행도 빼지만, 넓은 키 테이블은 그 값을 `None`으로 두고 행을
  유지합니다. `clean=False`는 기관 원문 그대로 둡니다.
- **단위 주의.** 금액 컬럼은 단위를 이름에 담았습니다 -- 아파트 실거래가는 **만원**
  (`deal_amount_manwon`·`deposit_manwon`·`monthly_rent_manwon`), 조달청은 **원**
  (`estimated_price_krw`·`budget_amount_krw`), 관세청 `export_usd` 등은 **USD**입니다. 그래도
  여러 서비스를 한 표로 합쳐 더할 때는 단위를 맞추세요.
- **탐색.** 어떤 서비스·오퍼레이션이 있는지는 `datagokr list`로 봅니다. Python에선 서비스
  목록은 `catalog.services()`, 한 서비스의 오퍼레이션은 `catalog.operations("weather")`,
  정리된 열 스키마는 `catalog.fields("weather", "forecast")`(CLI는 `datagokr fields`)로 봅니다.
  각 오퍼레이션이 받는 옵션은 `datagokr <서비스> <오퍼레이션> --help`.
- **에러·운영.** reason 코드, 활용신청 승인 방식, 트래픽 한도는 [docs/errors.md](https://github.com/seokhoonj/pydatagokr/blob/main/docs/errors.md)에
  정리돼 있습니다.

## 4. 커맨드라인

```bash
datagokr --version                                    # 버전 출력
datagokr list                                         # 서비스·오퍼레이션 (오프라인, 키 불필요)
datagokr fields weather forecast                      # 한 오퍼레이션의 정리된 열 스키마 (오프라인)
datagokr holidays --year 2026                         # 공휴일
datagokr realestate apt_trade 11110 --deal-ym 202401  # 아파트 매매 실거래가

# 코드 찾기 (오프라인, 키 불필요) -- 위·경도/지역명을 서비스가 받는 코드로
datagokr grid 37.5714 126.9658                        # 위/경도 -> 기상청 격자 nx ny (60 127)
datagokr lawd 종로구                                   # 지역명 -> 법정동코드 LAWD_CD (11110)
datagokr land-region 서울                              # 지역명 -> 중기육상예보 REGID (11B00000)
datagokr temp-region 서울                              # 지역명 -> 중기기온예보 REGID (11B10101)
```

호출 형태는 `datagokr <서비스> <오퍼레이션> [옵션]`입니다. 기본 출력은 읽기 좋은
요약이고, `--json`을 붙이면 전체 결과를 JSON으로 냅니다. 서비스별 전체 명령과 옵션,
코드를 찾는 법은 위 표의 문서를 참고하세요.

## 5. AI 코딩 에이전트에서 사용

이 저장소는 Claude Code·Codex용 플러그인 마켓플레이스도 겸합니다. `list`·`weather`·
`airquality`·`holidays`·`realestate`·`midforecast`·`procurement`·`customs`·`kofia`를
같은 이름의 `datagokr` 명령을 호출하는 스킬로 제공합니다. 먼저 위에서 패키지를
설치하세요(`list`는 키 없이, 조회는 키 필요).

### 5.1 Claude Code

Claude Code 채팅창에서 마켓플레이스를 추가하고 설치합니다:

```
/plugin marketplace add seokhoonj/pydatagokr   # 마켓플레이스 등록
/plugin install datagokr@pydatagokr            # 플러그인 설치
```

그런 다음 평범하게 물어보거나("서울 미세먼지 알려줘", "종로구 아파트 매매 실거래가"),
스킬을 직접 호출하세요: `/datagokr:realestate apt_trade 11110 --deal-ym 202401`.

### 5.2 Codex

터미널에서 마켓플레이스를 추가하고 설치합니다:

```
codex plugin marketplace add seokhoonj/pydatagokr   # 마켓플레이스 등록
codex plugin add datagokr@pydatagokr                # 플러그인 설치
```

스킬은 관련 요청에 반응하며, `datagokr <서비스> <오퍼레이션>`으로 직접 실행해도 됩니다.

### 5.3 플러그인 없이 (symlink)

플러그인으로 설치하지 않고 쓰려면, 스킬을 스킬 디렉터리에 symlink한 뒤 접두사
(`datagokr:`) 없이 `/weather`처럼 부르면 됩니다:

```sh
ln -s "$PWD/plugins/datagokr/skills/weather" ~/.claude/skills/weather   # Claude Code → /weather
ln -s "$PWD/plugins/datagokr/skills/weather" ~/.codex/skills/weather    # Codex → $weather
```

Claude Code는 바로 인식하고, Codex는 재시작해야 로딩됩니다.

## 6. 라이선스

**패키지 코드**는 MIT입니다(`LICENSE` 참고).

**데이터**는 제공기관의 것입니다. 공공데이터법 제3조에 따라 공공데이터는 원칙적으로
상업적 이용이 허용되나, 특정 데이터셋이 이를 제한하거나 기관이 제공을 중단할 수
있습니다(제28조). 데이터를 재배포하기 전에 해당 데이터셋의 이용 조건을 확인하세요.
