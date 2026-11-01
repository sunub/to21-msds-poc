"""항목별 중간 형식(모델 응답)을 TO21 v0.6 JSON으로 펼친다 (B, ADR-001·002·004).

파일을 읽거나 쓰지 않고 모델을 부르지 않는다. 모양은 TO21 스키마(msds_item_schema)를 따라 만든다.
- 스키마에 있는 칸은 모두 넣는다(없으면 null, 배열은 []). 스키마에 없는 중간 형식 칸(line, lines,
  comp_name, comp_cas, start, end)은 남지 않는다.
- 형식(pattern)이 정해진 칸의 빈 글자("")는 null로 둔다. 중간 형식에는 형식 조건이 없어 모델이 ""를 쓴다.
- seq, Q의 status·dp·note, comp_ref, 서술 문장, extras의 쪽·항 번호, 근거(evidence)는 코드가 채운다.
- 원문 줄로 확인되는 값(H·P 코드, 개정 횟수, 메타 값 없음, 전화번호, 비어 있는 유해성 분류)은 A의 함수 전에
  source_rules.apply_source_rules가 고친다. 15항 기준농도는 펼치기 전에 근거 줄로 source_rules.fill_thresholds가
  채우거나 바로잡는다 (ADR-029).
- 값 없는 행의 표기는 A의 규칙 함수(msds.common.conventions.apply)에 맡긴다.
- 15항 화평법 행은 값이 있는데 해당 여부가 비면 '해당'으로 채운다 (사용자 결정 10/29).
"""
from __future__ import annotations

import functools
import importlib
import importlib.util
import json
import re
from functools import lru_cache
from collections import Counter, defaultdict

from msds.common.merge import DICTIONARY_VERSION, SCHEMA_VERSION, now_kst
from msds.common.paths import to21_file
from msds.common.schema import load_schema, msds_item_schema
from msds.extract.inputs import SECTION_NOS, Line, line_index, line_parents
from msds.extract.section_specs import META_REVISION_FIELDS
from msds.extract.source_rules import apply_source_rules, clear_numberless_thresholds, fill_thresholds

_NO_VALUE = {"자료없음", "해당없음", "미기재"}
_NOTE = re.compile(r"^(?P<base>[^()（）]+?)\s*[(（](?P<note>[^()（）]+)[)）]$")   # 상태어(괄호 설명), Q.note
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_BULLET = re.compile(r"^\s*(?:[-–](?!\d)|[•·○●◦■□▪*ο]|[①-⑳]|\(?\d{1,2}\)|\d{1,2}\.(?!\d)"
                     r"|\(?[가나다라마바사아자차카타파하거너더러머][.)])\s*")   # 9항은 하 다음 거·너·더·러·머
_PIPE_LEAD = re.compile(r"^\|\s*")    # version9: 불릿 기호가 표 칸처럼 ' | '로 묶여 온다
_COLON = re.compile(r"[:：]")
_COMP_KEYS = ("comp_name", "comp_cas")
_SINGLE_COMP_KEYS = {"exposure_limits", "toxicity", "cmr", "ecotox", "regulations", "intl_class"}   # 성분이 하나면 성분 표기 없는 행도 그 성분 (R10, 명세서 1_항목정의 예시 '1')
# 15항에서 제품 단위로 판정하는 법령. 성분이 하나여도 MIX로 둔다 (1_항목정의 dangerous_goods·waste 예시 'MIX',
# TO21 정합성 설계서 v0.4 29·40장: 15항은 성분 × 규제 항목으로 판정하고 위험물만 '제품'으로 판정)
_PRODUCT_LAWS = {"DG", "WASTE"}
_SOURCE_MAX = 200    # TO21 evidence.source_text: 200자 이내


def _defs() -> dict:
    return load_schema()["$defs"]


def _resolve(node: dict) -> dict:
    ref = node.get("$ref")
    return _defs()[ref.rsplit("/", 1)[1]] if ref else node


# ── 숫자 묶음 ──────────────────────────────────────────

def _dp(raw: str | None, num) -> int | None:
    """num을 raw에 적힌 그대로 볼 때의 소수 자릿수. raw에서 같은 수를 못 찾으면 None."""
    if raw is None or num is None:
        return None
    for tok in _NUM.findall(raw):
        t = tok.replace(",", "")
        if float(t) == abs(num):
            return len(t.split(".")[1]) if "." in t else 0
    return None


def _word_key(text: str) -> str:
    return re.sub(r"[\W_]+", "", text).lower()     # 동의어 사전: 비교는 공백·구두점 제거 후


@functools.cache
def _dictionary() -> dict:
    return json.loads(to21_file("dictionary").read_text(encoding="utf-8"))


@functools.cache
def _status_words() -> dict[str, str]:
    """상태어 표기 → Q 상태. C7 값과 동의어 사전 status의 표기다. Q 상태가 아닌 '해당'(15항 해당 여부)은 뺀다."""
    enum = next(b for b in _defs()["Q"]["properties"]["status"]["anyOf"] if b.get("type") == "string")["enum"]
    words = {_word_key(s): s for s in enum if s != "값있음"}
    for status, variants in _dictionary()["status"].items():
        if status in enum:
            words.update({_word_key(v): status for v in variants})
    return words


def status_word(text: str | None) -> tuple[str | None, str | None]:
    """값 대신 적힌 상태어면 (상태, 괄호 설명). '해당없음(불연성)' → ('해당없음', '불연성'), '-' → 미기재 (R15)."""
    text = (text or "").strip()
    if text in ("-", "–"):
        return "미기재", None
    if status := _status_words().get(_word_key(text)):
        return status, None
    if (m := _NOTE.match(text)) and (status := _status_words().get(_word_key(m["base"]))):
        return status, m["note"].strip()
    return None, None


def fill_q(qm: dict | None) -> dict | None:
    """QM(모델이 쓴 숫자 묶음)에 status·dp·note를 더해 TO21 Q로 만든다."""
    if qm is None:
        return None
    q = {k: qm.get(k) for k in _defs()["Q"]["properties"]}
    num = next((q[k] for k in ("value", "lower", "upper") if q[k] is not None), None)
    q["status"], q["note"] = status_word(q["raw"]) if num is None else ("값있음", None)
    q["dp"] = _dp(q["raw"], num)
    return q


def status_to_q(row: dict) -> dict:
    """값 대신 상태어만 적힌 text_value는 q의 상태로 옮긴다 (TO21 예제 25 FLAMMABILITY, 2_공통구조 Q.status).
    값이 모두 빈 행의 출처(data_source)에 적힌 상태어도 칸이 밀린 것이라 옮긴다. 상태어는 출처가 아니다."""
    if row.get("q") is not None:
        return row
    for k in ("text_value", "data_source"):
        if status_word(row.get(k))[0]:
            return {**row, "q": {"raw": row[k]}, k: None}
        if row.get(k):
            return row
    return row


@functools.cache
def _physchem_names() -> list[tuple[str, str | None]]:
    """물성 이름 표기(동의어 사전 physchem, R25) → 코드, 긴 이름부터. 스키마에 없는 묶음 표기(UEL+LEL)는 None."""
    node = _resolve(msds_item_schema()["properties"]["physchem"]["items"])["properties"]["prop_code"]
    codes = set(next(b for b in node["anyOf"] if b.get("type") == "string")["enum"])
    names = {_word_key(n): (c if c in codes else None) for c, ns in _dictionary()["physchem"].items() for n in ns}
    return sorted(names.items(), key=lambda x: -len(x[0]))


def physchem_code(text: str | None, exact: bool = False) -> str | None:
    """물성 이름을 사전에서 찾아 코드로 바꾼다. 원문 줄은 이름 뒤에 값이 이어지고 칸을 공백으로만 나눈 표도 있어
    앞머리로 비교하고(TO21 커버리지 점검과 같은 방식), 이름만 있는 제목은 exact로 통째로 비교한다."""
    key = _word_key(_strip_bullet(text or ""))
    return next((c for n, c in _physchem_names() if n and (key == n if exact else key.startswith(n))), None)


@functools.cache
def _flammability_names() -> tuple[str, ...]:
    """폭발 범위 상한/하한을 한 줄에 적은 이름(동의어 사전 physchem의 UEL+LEL 묶음 표기)."""
    return tuple(sorted((_word_key(n) for n in _dictionary()["physchem"].get("UEL+LEL", [])), key=len, reverse=True))


_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _flammability_pair(raw: str) -> tuple[dict, dict] | None:
    """원문 표기 하나 → (UEL QM, LEL QM). 숫자가 둘 이상이면 큰 수가 UEL, 작은 수가 LEL인 단일값이고, 단위는 마지막 숫자
    뒤의 표기다('4.0~76%' → 76 %, 4 %). 숫자 없이 상태어만 있으면 두 행 모두 그 원문이다. 그 밖에는 None."""
    nums = [float(x) for x in _NUMBER.findall(raw or "")]
    if len(nums) >= 2:
        tail = re.split(r"\d", raw)[-1]
        unit = re.sub(r"\s+\(.*$", "", tail).strip(" ~/,") or None     # 공백 뒤 괄호 설명은 떼고 붙은 괄호(%(V))는 둔다
        num = lambda v: int(v) if v.is_integer() else v
        return ({"raw": raw, "value": num(max(nums)), "unit": unit}, {"raw": raw, "value": num(min(nums)), "unit": unit})
    if not nums and status_word(raw)[0]:
        return {"raw": raw}, {"raw": raw}
    return None


def split_flammability(phys: list[tuple[int, dict]], lines_by_id: dict[str, Line]) -> list[tuple[int, dict]]:
    """폭발 범위 상한/하한을 한 줄에 적은 행을 UEL·LEL 두 행으로 나눈다 (골드·실버 6건과 같은 꼴).
    대상: 근거 줄이 묶음 이름(UEL+LEL)으로 시작하는 행, 숫자가 둘인 UEL·LEL 행, 짝 없이 상태어만 적힌 UEL·LEL 행.
    같은 줄의 UEL·LEL 행은 두 행으로 바꾼다. UEL·LEL이 줄마다 따로 적혀 있으면 그대로 둔다."""
    codes = {r.get("prop_code") for _, r in phys}
    out, done = [], set()
    for no, r in phys:
        line = r.get("line")
        text = _word_key(_strip_bullet(getattr(lines_by_id.get(line), "text", "") or ""))
        raw = (r.get("q") or {}).get("raw") or r.get("text_value") or ""
        code = r.get("prop_code")
        lone = code in ("UEL", "LEL") and ({"UEL", "LEL"} - {code}) - codes and not _NUMBER.search(raw)
        combined = any(text.startswith(n) for n in _flammability_names()) or lone
        pair = _flammability_pair(raw) if combined or (code in ("UEL", "LEL")
                                                       and len(_NUMBER.findall(raw)) >= 2) else None
        if pair is None or r.get("prop_code") not in (None, "UEL", "LEL"):
            out.append((no, r))
        elif line not in done:
            done.add(line)
            base = {k: v for k, v in r.items() if k not in ("prop_code", "q", "text_value")}
            out += [(no, {**base, "prop_code": "UEL", "q": pair[0], "text_value": None}),
                    (no, {**base, "prop_code": "LEL", "q": pair[1], "text_value": None})]
    return out


def fill_blank_from_line(row: dict, lines_by_id: dict[str, Line]) -> dict:
    """값·글자가 모두 빈 물성 행: 근거 줄에서 이름 다음 칸이 상태어(자료없음 등)면 그것을 값으로 둔다.
    모델이 '인화점 | 자료없음 | 자료없음'의 값 칸을 비운 일이 있었다. 상태어가 아니면 그대로 둔다."""
    q = row.get("q") or {}
    if q.get("raw") or any(q.get(k) is not None for k in ("value", "lower", "upper")) or row.get("text_value"):
        return row
    cells = [c.strip() for c in re.split(r"[|:：]", getattr(lines_by_id.get(row.get("line")), "text", "") or "")]
    value = next((c for c in cells[1:] if c), None)
    return {**row, "q": {"raw": value}} if value and status_word(value)[0] else row


def _extra_to_physchem(row: dict, code: str) -> dict:
    values = [s["value"] for s in row.get("statements") or [] if s.get("value")]
    return {"prop_code": code, "comp_name": row.get("comp_name"), "comp_cas": row.get("comp_cas"), "q": row.get("q"),
            "text_value": None if row.get("q") else ("; ".join(values) or None), "line": row.get("line")}


# ── 서술 문장 ──────────────────────────────────────────

def _strip_bullet(text: str) -> str:
    body = _PIPE_LEAD.sub("", _BULLET.sub("", text, count=1).strip(), count=1)
    return body.strip() or text.strip()


def _key_value(body: str) -> tuple[str | None, str]:
    """'키 : 값'(콜론 앞 30자 이하)이면 나눈다. 시각(09:00)과 주소(https://)의 콜론은 나누지 않는다."""
    m = _COLON.search(body)
    if m:
        i = m.start()
        key, value = body[:i].strip(), body[m.end():].strip()
        is_time = i > 0 and body[i - 1].isdigit() and body[i + 1:i + 2].isdigit()
        if key and value and len(key) <= 30 and not is_time and not value.startswith("//"):
            return key, value
    return None, body


def split_statements(lines: list[Line]) -> list[dict]:
    """빈 줄이 아닌 줄마다 STMT 하나. 불릿을 떼고 '키 : 값'을 나눈다. text는 원문 줄 그대로 (R14)."""
    out = []
    for line in lines:
        if not line.text.strip():
            continue
        key, value = _key_value(_strip_bullet(line.text))
        out.append({"seq": len(out) + 1, "key": key, "value": value, "refs": [], "cond": None,
                    "std_code": None, "match_score": None, "text": line.text})
    return out


# ── 성분 연결 ──────────────────────────────────────────

def _norm(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "").casefold()


def _component_in_line(text: str | None, by_key: dict[str, dict]) -> dict | None:
    """줄에 보이는 성분이 하나면 그 성분. 다른 이름 안에 든 이름(을 ⊂ 을 염)은 세지 않는다."""
    t = _norm(text)
    found = [k for k in by_key if k in t]
    found = [k for k in found if not any(k != o and k in o for o in found)]
    hits = {by_key[k]["seq"]: by_key[k] for k in found}
    return next(iter(hits.values())) if len(hits) == 1 else None


def _any_component(text: str | None, by_key: dict[str, dict]) -> bool:
    return any(k in _norm(text) for k in by_key)


def link_components(rows: list[dict], components: list[dict], lines_by_id: dict[str, Line] | None = None) -> list[dict]:
    """comp_name·comp_cas를 3항 성분의 seq(글자)인 comp_ref로 바꾼 새 행 목록. CAS 먼저, 다음 이름.
    둘 다 비었으면 근거 줄(lines_by_id)에 성분 이름·CAS가 하나만 보일 때 그 성분이다 ('- 이소부텐 : 자료없음' 목록).
    근거 줄에 성분이 없으면 부모 줄을 가까운 것부터 보고, 성분이 보이는 첫 부모에서 하나면 그 성분이다
    ('- 1,3 부타디엔 : 구분 1A' 아래 '· IARC : 2A'). 그래도 모르거나 어느 성분에도 안 맞으면 "MIX"."""
    parents = line_parents(list(lines_by_id.values())) if lines_by_id else {}
    by_cas = {_norm(c.get("cas_no")): c for c in components if _norm(c.get("cas_no"))}
    by_name: dict[str, dict] = {}
    for c in components:
        for n in (c.get("name"), c.get("name_en"), *(c.get("synonyms") or [])):
            if _norm(n):
                by_name.setdefault(_norm(n), c)
    out = []
    for r in rows:
        name = r.get("comp_name") or ""
        c = (by_cas.get(_norm(r.get("comp_cas"))) or by_name.get(_norm(name))
             or by_name.get(_norm(re.split(r"[,(（]", name)[0])))    # 'NATURAL GAS, LIQUIFIED'의 수식어를 뗀 이름
        if c is None and lines_by_id and not _norm(name) and not _norm(r.get("comp_cas")):
            line = lines_by_id.get(r.get("line"))
            for up in ([line, *parents.get(line.id, [])] if line else []):
                c = _component_in_line(up.text, {**by_name, **by_cas})
                if c or _any_component(up.text, {**by_name, **by_cas}):
                    break
        out.append({**{k: v for k, v in r.items() if k not in _COMP_KEYS},
                    "comp_ref": str(c["seq"]) if c else "MIX"})
    return out


_CMR_PREFIX = re.compile(r"^\s*(?:발암성|생식\s*세포\s*변이원성|생식\s*독성)\s*[:：]?\s*")
_CATEGORY_WORD = re.compile(r"^구분\s*(?=\d)")


def fix_cmr_class(rows: list[dict]) -> None:
    """CMR 등급(class)에서 '구분'과 유해성 이름을 뺀다 (R07, 기관 표기는 그대로). 상태어(C7)만 적혔으면 등급을 비우고
    status로 옮긴다. '분류되지않음'처럼 사전에만 있는 표기는 기관 표기로 보고 그대로 둔다."""
    status = _resolve(msds_item_schema()["properties"]["cmr"]["items"])["properties"]["status"]
    words = {_word_key(w): w for w in next(b for b in status["anyOf"] if b.get("type") == "string")["enum"]
             if w != "값있음"}
    for r in rows:
        if not r.get("class"):
            continue
        c = _CATEGORY_WORD.sub("", _CMR_PREFIX.sub("", r["class"])).strip()
        if _word_key(c) in words:
            r["class"], r["status"] = None, words[_word_key(c)]
        else:
            r["class"] = c or None


def clear_descriptor_without_value(rows: list[dict]) -> None:
    """값(숫자)이 없는 독성 행의 지표를 정한다. 상태가 값 없음(자료없음 등)이면 비워 A의 규칙이 '결과기술'(혼합물 급성은
    'ATE')로 채우게 하고, 설명만 있는 행(값있음)은 '결과기술'로 둔다. 골드·실버의 숫자 없는 독성 행은 모두 그렇게 적혀
    있다. 모델이 '- 이소부텐 : 자료없음'에 LD50을 적은 일이 있었다(11/01 실행)."""
    for r in rows:
        q = r.get("q") or {}
        if all(q.get(k) is None for k in ("value", "lower", "upper")):
            r["descriptor"] = None if r.get("status") in _NO_VALUE else "결과기술"


_SECOND_UNIT = re.compile(r"^\s*(?P<a>-?\d[\d.,]*\s*[^\s\d()（）][^()（）]*?)\s*[(（]\s*"
                          r"(?P<b>-?\d[\d.,]*\s*[^\s\d()（）][^()（）]*?)\s*[)）]?\s*$")
_TOTAL = re.compile(r"^\s*(?:total|합\s*계|계|sum)\s*$", re.IGNORECASE)


def split_second_unit(row: dict) -> list[dict]:
    """노출기준 값이 '0.5 ppm (1.6 mg/m3)'처럼 단위 둘로 적혔으면 단위마다 한 행 (골드 S016, 실버 M002).
    닫는 괄호가 빠져도 같다. 두 쪽 모두 숫자와 단위가 있을 때만 나눈다."""
    m = _SECOND_UNIT.match((row.get("q") or {}).get("raw") or "")
    if not m:
        return [row]
    from msds.extract.rows import parse_qm      # rows가 펼치기 결과 형식을 쓰므로 여기서 부른다
    parts = [parse_qm(m[k].strip()) for k in ("a", "b")]
    if not all(p.get("value") is not None and p.get("unit") for p in parts) or parts[0]["unit"] == parts[1]["unit"]:
        return [row]
    return [{**row, "q": p} for p in parts]


def drop_repeated(pairs: list[tuple[int, dict]]) -> list[tuple[int, dict]]:
    """원문 줄까지 같은 행은 모델이 반복한 것이라 처음 것만 남긴다. 줄이 없거나 다르면 남긴다."""
    seen, out = set(), []
    for no, r in pairs:
        key = json.dumps(r, sort_keys=True, ensure_ascii=False) if r.get("line") else None
        if key is None or key not in seen:
            out.append((no, r))
            seen.add(key)
    return out


# ── 15항 화평법 해당 여부 ──────────────────────────────

def _has_value(text: str | None) -> bool:
    t = re.sub(r"\s+", "", text or "")
    return bool(t) and t not in _NO_VALUE | {"비해당"}


_KREACH_NEGATIVE_EXTRA = ("규제되지않음", "비위험물", "미규정", "unlisted")  # A의 답 10/30, A-1


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "").lower()


@lru_cache(maxsize=1)
def _kreach_negatives() -> frozenset[str]:
    """부정 표현: TO21 사전 status.해당없음(실행 때 읽음, 못 읽으면 없음) + A의 추가 표기."""
    try:
        from msds.extract.section_prompts import _dictionary
        words = _dictionary()["status"]["해당없음"]
    except Exception:
        words = []
    return frozenset({_norm(w) for w in words} | set(_KREACH_NEGATIVE_EXTRA))


def fill_kreach_applicable(regulations: list[dict]) -> None:
    """화평법(KREACH) 행의 해당 여부(applicable)가 비었을 때 값(value_raw 또는 threshold)으로 채운다.
    값이 부정 표현이면 '비해당', '문의' 안내문이면 비워 두고, 그 밖에 값이 있으면 '해당'이다.
    값 없는 행과 다른 법령 행은 그대로 둔다 (사용자 결정 10/29, A-1 답 10/30)."""
    for r in regulations:
        if r.get("law") != "KREACH" or r.get("applicable") is not None:
            continue
        for text in (r.get("value_raw"), (r.get("threshold") or {}).get("raw")):
            t = _norm(text)
            if t in _kreach_negatives():
                r["applicable"] = "비해당"
            elif _has_value(text) and "문의" not in t:
                r["applicable"] = "해당"
            else:
                continue
            break


def _law_of(row: dict) -> str | None:
    """행의 법령. 비면 항목 코드에서 정한다. 항목 코드는 법령 코드로 시작한다 (명세서 5-6, OSH_MEASURE → OSH)."""
    if row.get("law") is not None:
        return row["law"]
    law = _resolve(msds_item_schema()["properties"]["regulations"]["items"])["properties"]["law"]
    laws = next(b for b in law["anyOf"] if b.get("type") == "string")["enum"]
    code = row.get("item_code") or ""
    return next((x for x in laws if code == x or code.startswith(x + "_")), None)


def fill_law(regulations: list[dict]) -> None:
    """법령(law)이 비면 항목 코드에서 채운다."""
    for r in regulations:
        r["law"] = _law_of(r)


# ── 표기 규칙 자리 (ADR-004) ───────────────────────────

def apply_conventions(msds_item: dict) -> dict:
    """A의 msds.common.conventions.apply가 있으면 부르고, 없으면 그대로 돌려준다."""
    name = "msds.common.conventions"
    if importlib.util.find_spec(name) is None:
        return msds_item
    apply = getattr(importlib.import_module(name), "apply", None)
    return apply(msds_item) if callable(apply) else msds_item


# ── 펼치기 ─────────────────────────────────────────────

def _shape(node: dict, value, lines_by_id: dict[str, Line]):
    """TO21 스키마 조각 node의 모양으로 value를 펼친다. 스키마에 없는 칸은 버리고, 없는 칸은 null·[]로 둔다."""
    ref = node.get("$ref")
    if ref == "#/$defs/Q":
        return fill_q(value)
    if ref:
        out = _shape(_resolve(node), value, lines_by_id)
        if ref == "#/$defs/STMT" and out["text"] is None:      # 원문 줄은 line에서 채운다
            line = lines_by_id.get(value.get("line"))
            out["text"] = line.text if line else None
        return out
    if "anyOf" in node:
        branch = next(b for b in node["anyOf"] if b.get("type") != "null")
        if value is None or (value == "" and "pattern" in branch):   # 형식이 정해진 칸의 빈 글자는 값 없음
            return None
        return _shape(branch, value, lines_by_id)
    if node.get("type") == "object" and "properties" in node:
        value = value or {}
        return {k: _shape(sub, value.get(k), lines_by_id) for k, sub in node["properties"].items()}
    if node.get("type") == "array":
        rows = [_shape(node["items"], v, lines_by_id) for v in value or []]
        if "seq" in _resolve(node["items"]).get("properties", {}):
            for i, r in enumerate(rows, 1):
                r["seq"] = i
        return rows
    return value


def expand_msds(sections: dict[int, dict | None], lines_by_id: dict[str, Line],
                msds_index: int, evidence_method: str) -> tuple[dict, list[dict]]:
    """MSDS 한 건의 항별 응답을 TO21 msds 항목 하나로 펼친다. 반환: (msds 항목, 문제 목록)."""
    props = msds_item_schema()["properties"]
    ids = list(lines_by_id)
    pos = {lid: i for i, lid in enumerate(ids)}
    problems: list[dict] = []
    evidence: list[dict] = []

    def problem(no: int, kind: str, detail: str) -> None:
        problems.append({"msds_index": msds_index, "section": no, "kind": kind, "detail": detail})

    def evidence_row(field: str, line: Line | None, text: str | None = None, review: bool | None = None) -> None:
        evidence.append({"field": field, "page": line.page if line else None, "bbox": None,
                         "source_text": (text or line.text)[:_SOURCE_MAX] if line else None, "confidence": None,
                         "method": evidence_method, "needs_review": review})

    def add_evidence(no: int, field: str, line_id: str, text: str | None = None) -> None:
        line = lines_by_id.get(line_id)
        if line is None:
            problem(no, "bad_line", f"{field}: {line_id}")
        evidence_row(field, line, text, None if line else True)

    def walk(no: int, value: dict, path: str) -> None:
        """행의 line, 객체의 lines, 안쪽 행 배열의 line을 근거로 옮긴다."""
        if value.get("line") is not None:
            add_evidence(no, path, value["line"])
        for k, lid in (value.get("lines") or {}).items():
            if lid is not None:
                add_evidence(no, f"{path}.{k}", lid)
        for k, v in value.items():
            if isinstance(v, list):
                for i, r in enumerate(v):
                    if isinstance(r, dict):
                        walk(no, r, f"{path}.{k}[{i}]")

    def narrative(no: int, row: dict, field: str) -> dict:
        start, end = row.get("start"), row.get("end")
        span: list[Line] = []
        bad = [x for x in dict.fromkeys((start, end)) if x not in lines_by_id]
        for x in bad:
            problem(no, "bad_line", f"{field}: {x}")
        if bad:
            evidence_row(field, None, review=True)
        elif pos[start] > pos[end]:
            problem(no, "bad_range", f"{field}: {start} > {end}")
            evidence_row(field, lines_by_id[start], review=True)
        else:
            span = [lines_by_id[lid] for lid in ids[pos[start]:pos[end] + 1]]
            # 원문 대조는 한 쪽 안에서 찾으므로 시작 쪽의 줄만 근거로 쓴다
            add_evidence(no, field, start, "\n".join(l.text for l in span if l.page == span[0].page))
            title = row.get("title_raw")
            if span and title and _norm(_strip_bullet(span[0].text)) == _norm(_strip_bullet(title)):
                span = span[1:]
        statements = split_statements(span)
        return {"item_code": row.get("item_code"), "title_raw": row.get("title_raw"),
                "status": "값있음" if statements else None, "statements": statements}

    # 1. 항별 응답을 TO21 키별로 모은다. 배열은 항 순서대로 잇는다.
    objects: dict[str, tuple[int, dict]] = {}
    rows: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for no in SECTION_NOS:
        resp = sections.get(no)
        if resp is None:
            problem(no, "missing_section", f"{no}항 응답 없음")
            continue
        for key, val in resp.items():
            if isinstance(val, list):
                rows[key] += [(no, r) for r in val]
            elif isinstance(val, dict):
                objects[key] = (no, val)

    # 1-1. 동의어 사전(R25)에 있는 물성 이름은 물성 행이다. 코드가 빈 물성 행은 원문 줄의 이름으로 채우고,
    #      9항 부가 행 가운데 제목이 물성 이름인 것은 그 코드의 물성 행이 없으면 물성 행으로 옮긴다.
    phys = [(no, r if r.get("prop_code") else {**r, "prop_code": physchem_code(getattr(lines_by_id.get(r.get("line")),
                                                                                        "text", None))})
            for no, r in rows["physchem"]]
    have, extras = {r["prop_code"] for _, r in phys}, []
    for no, r in rows["extras"]:
        code = physchem_code(r.get("title_raw"), exact=True) if no == 9 else None
        if code and code not in have and (r.get("q") is not None or r.get("statements")):
            have.add(code)
            phys.append((no, _extra_to_physchem(r, code)))
        else:
            extras.append((no, r))
    if len(extras) < len(rows["extras"]):      # 옮긴 행은 원문 순서 자리에 둔다
        phys.sort(key=lambda p: pos.get(p[1].get("line"), len(pos)))
    # 1-2. 폭발 범위 상한/하한 한 줄은 UEL·LEL 두 행으로, 값이 빈 행은 근거 줄의 상태어로 (모델 표기가 실행마다 달랐다)
    phys = [(no, fill_blank_from_line(r, lines_by_id)) for no, r in split_flammability(phys, lines_by_id)]
    rows["physchem"], rows["extras"] = phys, extras

    # 서술 구간(양 끝 포함 줄 위치)을 항마다 모은다. extras 거르기에 쓰므로 펼치기 전에 끝낸다 (ADR-022).
    # narrative()가 문장을 만드는 구간과 같다: 두 끝이 원문에 있고 start <= end.
    spans: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for no, r in rows["narratives"]:
        start, end = r.get("start"), r.get("end")
        if start in pos and end in pos and pos[start] <= pos[end]:
            spans[no].append((pos[start], pos[end]))

    # 2. TO21 키 순서대로 펼친다. 성분은 다른 행의 comp_ref가 가리키므로 먼저 만든다.
    # 성분표의 합계 행('Total | 100%')은 성분이 아니다. 남기면 단일 성분 문서가 두 성분이 된다 (S001)
    rows["components"] = [(no, r) for no, r in rows["components"]
                          if not (_TOTAL.match(r.get("name") or "") and not r.get("cas_no"))]
    components = _shape(props["components"], [r for _, r in rows["components"]], lines_by_id)
    item: dict = {}
    for key, node in props.items():
        if key in ("evidence", "validation"):
            item[key] = []
            continue
        if node.get("type") == "object":
            no, val = objects.get(key, (0, None))
            item[key] = _shape(node, val, lines_by_id)
            if val is not None:
                walk(no, val, key)
            continue
        pairs = rows.get(key, [])
        if key == "narratives":
            item[key] = _shape(node, [narrative(no, r, f"{key}[{i}]") for i, (no, r) in enumerate(pairs)],
                               lines_by_id)
            continue
        pairs = drop_repeated(pairs)
        if key == "exposure_limits":
            pairs = [(no, x) for no, r in pairs for x in split_second_unit(r)]
        src = [r for _, r in pairs]
        if key == "extras":
            # 같은 항 서술 구간 안의 줄을 가리키는 extras는 서술 문장을 다시 쓴 것이라 버리고 항마다 센다
            kept, dropped = [], Counter()
            for no, r in pairs:
                at = pos.get(r.get("line"))
                if at is not None and any(s <= at <= e for s, e in spans.get(no, ())):
                    dropped[no] += 1
                else:
                    kept.append((no, r))
            for no, n in dropped.items():
                problem(no, "extras_in_narrative", f"{n}행")
            pairs = kept
            src = [{**r, "section_no": no,
                    "page": lines_by_id[r["line"]].page if r.get("line") in lines_by_id else None}
                   for no, r in pairs]
        if "comp_ref" in node["items"].get("properties", {}):
            src = link_components(src, components, lines_by_id)
            for i, ((no, r), linked) in enumerate(zip(pairs, src)):
                if linked["comp_ref"] == "MIX" and (_norm(r.get("comp_name")) or _norm(r.get("comp_cas"))):
                    problem(no, "unlinked_component", f"{key}[{i}]: {r.get('comp_name')} / {r.get('comp_cas')}")
            if key in _SINGLE_COMP_KEYS and len(components) == 1:
                src = [{**r, "comp_ref": str(components[0]["seq"])}
                       if r["comp_ref"] == "MIX" and _law_of(r) not in _PRODUCT_LAWS else r for r in src]
        if {"q", "text_value"} <= _resolve(node["items"]).get("properties", {}).keys():
            src = [status_to_q(r) for r in src]
        if key == "regulations":
            src = fill_thresholds(src, lines_by_id)      # 근거 줄의 'N% 이상'으로 기준농도 (ADR-029)
        item[key] = components if key == "components" else _shape(node, src, lines_by_id)
        if key == "regulations":
            fill_law(item[key])
            fill_kreach_applicable(item[key])
            clear_numberless_thresholds(item[key])       # 해당 여부를 정한 뒤, 숫자 없는 기준농도('비해당')를 비운다
        if key == "cmr":
            fix_cmr_class(item[key])
        if key == "toxicity":
            clear_descriptor_without_value(item[key])
        if key == "exposure_limits":
            for r in item[key]:
                if r.get("standard") == "생물학적":      # 생물학적 노출기준은 늘 BEI다 (골드·실버 33행)
                    r["limit_type"] = "BEI"
                q = r.get("q") or {}
                if q and all(q.get(k) is None for k in ("value", "lower", "upper")) and re.search(r"단순\s*질식", q.get("raw") or ""):
                    q["status"] = "해당없음"            # 단순 질식제: 수치 기준이 없다 (골드 S003, 실버 S001·S003)
        for i, (no, r) in enumerate(pairs):
            walk(no, r, f"{key}[{i}]")

    # 3. 개정 정보는 16항 값이 1항 값보다 우선한다. 16항에 값이 없을 때만 1항 값을 둔다.
    no, rev = objects.get("meta_revision", (16, None))
    rev_lines = (rev or {}).get("lines") or {}
    for f in META_REVISION_FIELDS:
        if rev and rev.get(f) is not None:
            item["meta"][f] = rev[f]
            evidence[:] = [e for e in evidence if e["field"] != f"meta.{f}"]
            if rev_lines.get(f) is not None:
                add_evidence(no, f"meta.{f}", rev_lines[f])

    item["evidence"] = evidence
    return item, problems


def to_to21(doc_meta: dict, parts: list[dict[int, dict]], lines: list[Line],
            engine: str) -> tuple[dict, list[dict]]:
    """doc_meta: manifest 행(doc_id, source_file, pages, text_layer, language).
    parts: MSDS마다 {항 번호: 그 항의 중간 형식 응답(dict) 또는 None}.
    반환: (TO21 문서 {"doc": {...}, "msds": [...]}, 문제 목록)."""
    method = "텍스트층" if doc_meta.get("text_layer") == "정상" else "OCR"
    lines_by_id = line_index(lines)
    msds, problems = [], []
    for i, sections in enumerate(parts):
        item, p = expand_msds(sections, lines_by_id, i, method)
        apply_source_rules(item, lines, len(parts) == 1)      # 원문 줄로 확인되는 값 고치기 (ADR-029)
        msds.append(apply_conventions(item))
        problems += p
    doc = {
        "doc_id": doc_meta["doc_id"],
        "source_file": doc_meta["source_file"],
        "page_count": int(doc_meta["pages"]) if doc_meta.get("pages") else None,
        "text_layer": doc_meta.get("text_layer") or None,
        "language": doc_meta.get("language") or None,
        "msds_count": len(parts),
        "schema_version": SCHEMA_VERSION,
        "dictionary_version": DICTIONARY_VERSION,
        "extraction": {"engine": engine, "extracted_at": now_kst()},
    }
    return {"doc": doc, "msds": msds}, problems
