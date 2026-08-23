"""Resolve a Korean place name to the vendor code a data.go.kr service takes: a 법정동
시군구 code (LAWD_CD) for `realestate`, and a 중기예보 REGID for `midforecast` (the land
zone and the temperature city are separate code sets). A 시군구 name repeats across 시도
(many "중구"), so an ambiguous query raises `ValueError` listing the candidates; qualify it
with a 시도 ("서울 중구") or the parent 시 ("수원시 장안구") to pin one down."""

from __future__ import annotations

import unicodedata

from ._regions_data import LAND_ZONES, SIGUNGU, TEMP_CITIES

__all__ = ["lawd_code", "land_region", "temp_region"]

# 도 abbreviations a 시도 substring test misses (충남 is not a substring of 충청남도). The
# 특별시/광역시/특별자치도 short forms ("서울", "강원", "전북") are substrings, so they need
# no entry here.
_SIDO_ALIAS = {"충북": "충청북도", "충남": "충청남도", "경북": "경상북도", "경남": "경상남도"}


def _sido_matches(hint: str, sido: str) -> bool:
    return hint in sido or _SIDO_ALIAS.get(hint) == sido


def lawd_code(query: str) -> str:
    """The 5-digit 법정동 시군구 code (LAWD_CD) for ``query``: "종로구" -> "11110",
    "서울 중구" -> "11140", "수원시 장안구" -> "41111". The last whitespace-separated token is
    the 시군구 (a 일반구 name may be a suffix, e.g. "장안구" of "수원시장안구"); any leading
    token qualifies it by 시도 or parent 시. Raises ``ValueError`` if nothing matches or the
    name is ambiguous (the message lists the candidates)."""
    # NFC-normalize so a decomposed-Hangul query (NFD, as macOS clipboards produce) matches
    # the composed names in the table.
    tokens = unicodedata.normalize("NFC", query).split()
    if not tokens:
        raise ValueError(f"no 시군구 matches {query!r}")
    name = tokens[-1]
    hints = tokens[:-1]
    # A 일반구 is stored as "<시>구" (e.g. "수원시장안구"), so a suffix match must land on that
    # 시-seam -- otherwise "천안 남구" would silently match "천안시동남구" (천안 has no 남구).
    candidates = [
        (sido, sigungu, code)
        for (sido, sigungu, code) in SIGUNGU
        if sigungu == name
        or (sigungu.endswith(name) and sigungu[: -len(name)].endswith("시"))
    ]
    # Each leading token narrows independently -- a 시도 ("경기도") or the parent 시 name as a
    # prefix ("수원시") -- so a fully qualified "경기도 수원시 장안구" resolves as well as the
    # bare "수원시 장안구", instead of the two being mashed into one unmatchable hint.
    for hint in hints:
        candidates = [
            (sido, sigungu, code) for (sido, sigungu, code) in candidates
            if _sido_matches(hint, sido) or sigungu.startswith(hint)
        ]
    if not candidates:
        raise ValueError(f"no 시군구 matches {query!r}")
    if len(candidates) > 1:
        listing = ", ".join(f"{sido} {sigungu}" for (sido, sigungu, _) in candidates)
        raise ValueError(
            f"{query!r} matches several 시군구: {listing} -- add the 시도 to disambiguate"
        )
    _, _, code = candidates[0]
    return code


def land_region(query: str) -> str:
    """The 중기육상예보 (getMidLandFcst) REGID for ``query`` (e.g. "서울" -> "11B00000").
    Raises ``ValueError`` if nothing matches or the name is ambiguous."""
    return _resolve_named(query, LAND_ZONES, "육상예보구역")


def temp_region(query: str) -> str:
    """The 중기기온예보 (getMidTa) 도시 REGID for ``query`` (e.g. "서울" -> "11B10101").
    Raises ``ValueError`` if nothing matches or the name is ambiguous."""
    return _resolve_named(query, TEMP_CITIES, "기온 도시")


def _resolve_named(query: str, table: tuple[tuple[str, str], ...], label: str) -> str:
    """Match ``query`` against ``table`` of (name, code): a 도 abbreviation is expanded to its
    full 시도 name first, then an exact name wins outright, otherwise a *prefix* match. Raises
    ``ValueError`` on no match, or on an ambiguous one (the message lists each candidate with
    its code and points at passing the code directly)."""
    normalized = unicodedata.normalize("NFC", query).strip()
    # A 도 abbreviation ("경북") is not a prefix of its full name ("경상북도"), so without this
    # expansion it falls through to a match that lands INSIDE an unrelated name: "경북" is a
    # substring of "함경북도", which silently resolved 경상북도 to a North Korean zone. Expand via
    # the same alias table lawd_code uses -- its targets ("경상북도", "충청북도") are exactly the
    # names LAND_ZONES/TEMP_CITIES carry -- then match a member, never an interior substring.
    resolved = _SIDO_ALIAS.get(normalized, normalized)
    # One zone can name several regions in a single entry ("서울.인천.경기"); split on the dot so
    # every member ("인천", "경기") resolves, not only the leading one. An exact member wins
    # outright; otherwise a member-prefix match ("강원" -> 강원영동/영서). Prefix is anchored to a
    # member start, so "경북" still cannot land inside "함경북도".
    exact = [(name, code) for (name, code) in table
             if any(member == resolved for member in name.split("."))]
    candidates = exact or [(name, code) for (name, code) in table
                           if any(member.startswith(resolved) for member in name.split("."))]
    if not candidates:
        raise ValueError(f"no {label} matches {query!r}")
    if len(candidates) > 1:
        # Some names collide outright (two bare "광주" 예보구역, 경기 vs 전남) with no finer name
        # to give, so the actionable escape is the code itself, not "a more specific name".
        listing = ", ".join(f"{name} ({code})" for (name, code) in candidates)
        raise ValueError(
            f"{query!r} matches several {label}: {listing} -- pass the code directly as "
            f"regid=, or use a more specific name")
    _, code = candidates[0]
    return code
