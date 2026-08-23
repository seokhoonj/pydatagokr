import pytest

from pydatagokr import land_region, lawd_code, temp_region


def test_lawd_unique():
    assert lawd_code("종로구") == "11110"


def test_lawd_ambiguous_lists_every_candidate():
    # 중구 exists in five 시도; the error must name them ALL and ask for a 시도 qualifier.
    with pytest.raises(ValueError) as exc:
        lawd_code("중구")
    msg = str(exc.value)
    for candidate in ("서울특별시 중구", "부산광역시 중구", "대구광역시 중구",
                      "대전광역시 중구", "울산광역시 중구"):
        assert candidate in msg


def test_lawd_sido_qualifier():
    assert lawd_code("서울 중구") == "11140"


def test_lawd_sido_alias():
    # 경남 is not a substring of 경상남도, so the alias table must map it -- both forms resolve
    # to the same vendor code (a fixed oracle, not one call compared against another).
    assert lawd_code("경남 고성군") == "48820"
    assert lawd_code("경상남도 고성군") == "48820"


def test_lawd_ilban_gu_by_parent_city():
    # 일반구: name stored as "수원시장안구"; the bare 구, the parent-시 qualifier, and the joined
    # form all resolve to the one code.
    assert lawd_code("수원시장안구") == "41111"
    assert lawd_code("수원시 장안구") == "41111"
    assert lawd_code("장안구") == "41111"


def test_lawd_code_accepts_nfd_hangul():
    # A decomposed-Hangul query (NFD, as macOS clipboards produce) is visually identical to the
    # composed table name but compares unequal without normalization.
    import unicodedata
    nfd = unicodedata.normalize("NFD", "종로구")
    assert nfd != "종로구"                         # genuinely decomposed
    assert lawd_code(nfd) == "11110"


def test_lawd_fully_qualified_three_token_query():
    # 시도 + parent 시 + 일반구: each leading token narrows independently, so the fully
    # qualified form resolves like the bare parent-시 form rather than mashing the two hints
    # into one unmatchable string.
    assert lawd_code("경기도 수원시 장안구") == "41111"


def test_lawd_suffix_requires_ilban_gu_seam():
    # A bare suffix must not match a 자치구 that merely ends with it: 천안 has no 남구 (only
    # 동남구/서북구), so "천안 남구" must fail loudly rather than return 천안시동남구's code.
    with pytest.raises(ValueError):
        lawd_code("천안 남구")


def test_lawd_unknown():
    with pytest.raises(ValueError):
        lawd_code("없는구")


def test_land_region():
    assert land_region("서울") == "11B00000"      # matches "서울.인천.경기"


def test_temp_region():
    assert temp_region("서울") == "11B10101"


def test_temp_region_unknown():
    with pytest.raises(ValueError):
        temp_region("없는도시")


def test_land_region_ambiguous_lists_candidates():
    # "전라" is a substring of several 육상예보구역, so the substring resolver must fail
    # loud with the candidates rather than silently pick the first.
    with pytest.raises(ValueError) as exc:
        land_region("전라")
    msg = str(exc.value)
    assert "전라남도" in msg and "전라도" in msg


def test_land_region_do_abbreviation_resolves_to_the_south_korean_zone():
    # A 도 abbreviation must expand to its full 시도 name, not fall through to an interior
    # substring match: "경북" sits inside "함경북도", which silently returned the North Korean
    # zone (11K10000) instead of 경상북도. The alias resolves it; the loud siblings still work.
    assert land_region("경북") == "11H10000"       # 경상북도, NOT 함경북도 (11K10000)
    assert land_region("경남") == "11H20000"       # 경상남도, NOT 함경남도 (11K20000)
    assert land_region("충북") == "11C10000" and land_region("충남") == "11C20000"
    assert land_region("함경북도") == "11K10000"   # the NK zone is still reachable by its full name


def test_temp_region_ambiguous_message_gives_the_code_to_use():
    # Two 예보구역 named exactly "광주" (경기 / 전남) cannot be told apart by a "more specific
    # name" -- the message must surface each code and point at passing regid directly.
    with pytest.raises(ValueError) as exc:
        temp_region("광주")
    msg = str(exc.value)
    assert "11B20702" in msg and "11F20501" in msg and "regid=" in msg


def test_land_region_resolves_a_non_leading_compound_zone_member():
    # One land zone names several regions in one entry ("서울.인천.경기"). Every member must
    # resolve to that zone's code, not only the leading "서울" -- matching the whole name by
    # prefix dropped "인천"/"경기", which are not a prefix of the compound string.
    assert land_region("서울") == "11B00000"
    assert land_region("인천") == "11B00000"
    assert land_region("경기") == "11B00000"
