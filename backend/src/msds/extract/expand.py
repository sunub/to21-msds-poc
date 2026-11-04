"""항목별 중간 형식(모델 응답)을 TO21 v0.6 JSON으로 펼친다 (B, ADR-001·002·004).

파일을 읽거나 쓰지 않고 모델을 부르지 않는다. 모양은 TO21 스키마(msds_item_schema)를 따라 만든다.
- 스키마에 있는 칸은 모두 넣는다(없으면 null, 배열은 []). 스키마에 없는 중간 형식 칸(line, lines,
  comp_name, comp_cas, start, end)은 남지 않는다.
- 형식(pattern)이 정해진 칸의 빈 글자("")는 null로 둔다. 중간 형식에는 형식 조건이 없어 모델이 ""를 쓴다.
- seq, Q의 status·dp·note, comp_ref, 서술 문장, extras의 쪽·항 번호, 근거(evidence)는 코드가 채운다.
- 원문 줄로 확인되는 값(H·P 코드, 개정 횟수, 메타 값 없음, 전화번호, 비어 있는 유해성 분류)은 A의 함수 전에
  source_rules.apply_source_rules가 고친다. 15항 기준농도는 펼치기 전에 근거 줄로 source_rules.fill_thresholds가
  채우거나 바로잡는다 (ADR-029). 9항 물성의 빈 값은 근거 줄의 상태어로 source_rules.fill_no_value가 채운다.
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
from msds.extract.inputs import EXTRACT_SECTIONS, SECTION_NOS, Line, line_index, line_parents
from msds.extract.section_specs import META_REVISION_FIELDS
from msds.extract.source_rules import apply_source_rules, clear_numberless_thresholds, fill_no_value, fill_thresholds

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


def _key_in_text(key: str, text: str | None) -> bool:
    """성분 이름·CAS가 줄에 보이는가. 공백을 뺀 글에서 찾되, 한 글자 이름은 낱말 전체만 본다
    ('물'이 '노출기준설정물질' 안에서 맞으면 항목 제목이 성분 줄이 된다. 공백을 빼면 낱말 경계가 사라져 원문에서 본다)."""
    if len(key) == 1:
        return bool(
            re.search(rf"(?<!\w){re.escape(key)}(?!\w)", (text or "").casefold())
        )
    return key in _norm(text)


def _component_in_line(text: str | None, by_key: dict[str, dict]) -> dict | None:
    """줄에 보이는 성분이 하나면 그 성분. 다른 이름 안에 든 이름(을 ⊂ 을 염)은 세지 않는다."""
    found = [k for k in by_key if _key_in_text(k, text)]
    found = [k for k in found if not any(k != o and k in o for o in found)]
    hits = {by_key[k]["seq"]: by_key[k] for k in found}
    return next(iter(hits.values())) if len(hits) == 1 else None


def _any_component(text: str | None, by_key: dict[str, dict]) -> bool:
    return any(_key_in_text(k, text) for k in by_key)


def link_components(rows: list[dict], components: list[dict], lines_by_id: dict[str, Line] | None = None) -> list[dict]:
    """comp_name·comp_cas를 3항 성분의 seq(글자)인 comp_ref로 바꾼 새 행 목록. CAS 먼저, 다음 이름.
    이름과 CAS가 서로 다른 성분을 가리키면 근거 줄·부모 줄에 적힌 쪽을, 둘 다 안 적혔으면 이름을 따른다
    (모델이 '1,3 부타디엔 | 106-97-8'처럼 맞는 이름에 다른 성분의 CAS를 붙였다. M004).
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
        by_n = by_name.get(_norm(name)) or by_name.get(_norm(re.split(r"[,(（]", name)[0]))   # 'NATURAL GAS, LIQUIFIED'의 수식어를 뗀 이름
        c = by_cas.get(_norm(r.get("comp_cas"))) or by_n
        if by_n is not None and c is not by_n:
            line = (lines_by_id or {}).get(r.get("line"))
            text = _norm(" ".join(x.text for x in ([line, *parents.get(line.id, [])] if line else [])))
            if not (_norm(c.get("cas_no")) in text and _norm(name) not in text):
                c = by_n
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
    """값(숫자)이 없는 독성 행의 지표는 상태와 관계없이 '결과기술'이다. 혼합물 급성의 값 없는 행도 같다
    (개발 골드 10건의 숫자 없는 독성 261행 모두. A 규칙이 채우는 'ATE'는 예제 1건에서 온 기본값이라 먼저 채운다).
    모델이 '- 이소부텐 : 자료없음'에 LD50을 적은 일이 있었다(11/01 실행).
    설명만 있는 행(값있음)의 q는 비운다 (골드 135행 모두). q에만 글이 있으면 statements로 옮겨 잃지 않는다."""
    for r in rows:
        q = r.get("q") or {}
        if all(q.get(k) is None for k in ("value", "lower", "upper")):
            r["descriptor"] = "결과기술"
            if r.get("status") not in _NO_VALUE and r.get("q") is not None and not q.get("status"):
                raw = (q.get("raw") or "").strip()
                if raw and not r.get("statements"):
                    r["statements"] = [{"seq": 1, "key": None, "value": raw, "refs": None, "cond": None, "std_code": None,
                                        "match_score": None, "text": raw}]
                r["q"] = None


_GROUP = re.compile(r"^\s*group\s*", re.IGNORECASE)
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


_LAW_HEAD = re.compile(r"법(?:률)?\s*(?:\([^)]*\)\s*)?에\s*(?:의한|따른|관한)\s*규제|등에\s*관한\s*법률\s*$")
_REG_STATUS = re.compile(r"^(?:규제되지않음|해당없음|해당사항없음|비해당|해당|해당됨|자료없음|등재되지않음)$")
_DOMESTIC = ("OSH", "CCA", "KREACH")


@functools.cache
def _reg_names() -> list[tuple[str, str]]:
    names = [(_word_key(n), c) for c, ns in _dictionary()["regulations"].items() for n in ns]
    return sorted((x for x in names if x[0]), key=lambda x: -len(x[0]))


def regulation_code(text: str | None) -> str | None:
    """규제 항목 이름을 동의어 사전(R25)에서 찾아 코드로. 이름 뒤에 값·괄호가 이어질 수 있어 앞머리로 비교한다."""
    key = _word_key(_strip_bullet(text or ""))
    return next((c for n, c in _reg_names() if key.startswith(n)), None)


def _reg_codes_in(text: str | None) -> set[str]:
    """글 안에 적힌 규제 항목 이름의 코드 전부 ('관리대상유해물질, 노출기준설정물질' → 두 코드).
    긴 이름부터 찾고 찾은 자리는 지워, 긴 이름 안의 짧은 이름(등록대상기존화학물질 ⊃ 기존화학물질)은 세지 않는다."""
    key, codes = _word_key(text or ""), set()
    for n, c in _reg_names():           # 긴 이름부터
        if n in key:
            codes.add(c)
            key = key.replace(n, "\0")
    return codes


def recode_regulations(rows: list[dict], lines_by_id: dict[str, Line], components: list[dict]) -> None:
    """국내 법령(산안법·화관법·화평법) 행의 항목 코드를 원문의 항목 이름으로 바로잡는다 (동의어 사전 R25).
    - 근거 줄(성분 줄이면 값 부분)에 적힌 항목이 하나면 그 코드 ('등록대상 기존 화학물질 (PEC)' → KREACH_REG.
      모델은 KREACH_EXIST). 여럿이면 모델 코드가 그중 하나일 때 그대로, 아니면 모호해 그대로 둔다 (M004 한 줄 여러 항목)
    - 성분 줄·상태 줄의 값이 비었거나 상태어면 제목 줄로 정한다. 글머리·들여쓰기 부모를, 없으면 위로 같은 목록의
      성분·상태 줄을 건너뛴 첫 줄을 본다. 법령 제목이면 코드 없음 (골드 M004 '가. 산업안전보건법에 의한 규제' 아래
      '- 부텐 1 : 해당없음'), 항목 이름 하나면 그 코드 (M013 '노출기준설정물질' 아래 성분 줄에 모델이 앞 제목의
      OSH_MEASURE를 붙였다), 그 밖에는 그대로 둔다. 값이 사전에 없는 글이면('노출기준설정대상물질') 그대로 둔다."""
    keys = {_norm(x): c for c in components for x in (c.get("name"), c.get("name_en"), c.get("cas_no"), *(c.get("synonyms") or []))
            if _norm(x)}
    ids = list(lines_by_id)
    at = {lid: i for i, lid in enumerate(ids)}
    parents = line_parents(list(lines_by_id.values()))

    def is_status(text: str) -> bool:
        return bool(_REG_STATUS.match(_word_key(text)))

    def listed(text: str) -> bool:          # 같은 목록의 성분 줄·상태 줄
        return _any_component(text, keys) or is_status(text)

    def heading(lid: str) -> str | None:
        ups = [x for x in parents.get(lid, []) if not listed(x.text)][:1]
        if not ups:
            for j in range(at[lid] - 1, max(at[lid] - 12, -1), -1):
                if not listed(lines_by_id[ids[j]].text):
                    ups = [lines_by_id[ids[j]]]
                    break
        if not ups:
            return None
        if _LAW_HEAD.search(ups[0].text):
            return "법령"
        codes = _reg_codes_in(ups[0].text)
        return next(iter(codes)) if len(codes) == 1 else None

    for r in rows:
        if _law_of(r) not in _DOMESTIC or r.get("line") not in at:
            continue
        text = lines_by_id[r["line"]].text
        thr = r.get("threshold") or {}
        num = next((thr[k] for k in ("value", "lower", "upper") if thr.get(k) is not None), None)
        if num is not None and f"{num:g}" not in text.replace(",", ""):
            continue                         # 기준농도가 근거 줄에 없다: 줄 번호가 틀린 행 (S016)
        if listed(text):
            if r.get("item_code") in _reg_codes_in(text):
                continue  # 모델 코드의 항목명이 이 줄에 적혀 있다. 제목보다 가깝다 (23번 '기존화학물질, 유독물질 (염화 수소…)')
            value = re.split(r"[:：|]", text, maxsplit=1)[1] if re.search(r"[:：|]", text) else ""
            if _any_component(text, keys) and value.strip() and not is_status(value):
                codes = _reg_codes_in(value)
                code = next(iter(codes)) if len(codes) == 1 else None
            else:
                code = heading(r["line"])
        else:
            codes = _reg_codes_in(text) if regulation_code(text) else set()
            code = next(iter(codes)) if len(codes) == 1 else None
        if r.get("item_code") is not None and code not in ("법령", None) and r["item_code"] in _reg_codes_in(text):
            continue                         # 모델 코드가 줄에 적힌 항목 중 하나
        if code == "법령":
            r["item_code"] = None
        elif code and code.split("_")[0] in _DOMESTIC and code != r.get("item_code"):
            r["item_code"], r["law"] = code, code.split("_")[0]


_REG_APPLICABLE = {"규제되지않음": "비해당", "해당없음": "비해당", "해당사항없음": "비해당", "비해당": "비해당",
                   "등재되지않음": "비해당", "해당": "해당", "해당됨": "해당", "자료없음": "자료없음"}


def add_missing_items(rows: list[dict], lines_by_id: dict[str, Line]) -> list[dict]:
    """15항 원문에 항목 이름만 적힌 제목 줄과 그 상태(같은 줄 ':' 뒤, 또는 바로 다음 상태 줄)가 있는데 그 코드의 행이
    하나도 없으면 더할 MIX 행들 (국내 법령만). 모델이 M013 '작업환경 측정대상물질' / '규제되지 않음.'을 뺐다.
    개발 골드는 15항에 적힌 국내 항목 이름 66개 모두 그 코드의 행이 있다. 범위는 규제 행 근거 줄의 처음~끝이다."""
    ids = list(lines_by_id)
    at = sorted(ids.index(r["line"]) for r in rows if r.get("line") in lines_by_id)
    if not at:
        return []
    have = {r.get("item_code") for r in rows}
    new = []
    for i in range(at[0], at[-1] + 1):
        text = _strip_bullet(lines_by_id[ids[i]].text)
        code = regulation_code(text)
        if not code or code.split("_")[0] not in _DOMESTIC or code in have or len(_reg_codes_in(text)) != 1:
            continue
        name = next(n for n, c in _reg_names() if c == code and _word_key(text).startswith(n))
        rest = _word_key(text)[len(name):]
        if not rest and i + 1 < len(ids):
            rest = _word_key(lines_by_id[ids[i + 1]].text)
        if rest in _REG_APPLICABLE:
            have.add(code)
            new.append({"law": code.split("_")[0], "item_code": code, "applicable": _REG_APPLICABLE[rest],
                        "comp_ref": "MIX", "line": ids[i]})
    return new


def dg_row_from_table(rows: list[dict], dangerous_goods: list[dict]) -> list[dict]:
    """규제 행이 있는데 위험물(DG) 행이 없고 위험물 표가 있으면 더할 DG_HAZMAT 행. 류(제N류)가 있으면 해당,
    상태어(해당없음·자료없음)면 그 상태로 정한다. 개발 골드는 15항이 있는 문서마다 DG_HAZMAT 행이 하나다
    (모델은 M013 '제4류 인화성액체 제2석유류'를 위험물 표에만 넣었다)."""
    if not rows or any(_law_of(r) == "DG" for r in rows):
        return []
    for d in dangerous_goods:
        cls = (d.get("class") or "").strip()
        applicable = "해당" if re.match(r"제\s*\d+\s*류", cls) else _REG_APPLICABLE.get(_word_key(cls))
        if applicable:
            return [{"law": "DG", "item_code": "DG_HAZMAT", "applicable": applicable, "comp_ref": "MIX", "line": d.get("line")}]
    return []


_LAW_LEVEL = re.compile(r"법(?:률)?\s*에\s*(?:의한|따른)\s*규제\s*[:：]?\s*(?P<v>.*)$")


def _law_level_item(row: dict, lines_by_id: dict[str, Line]) -> dict:
    """근거 줄이 '○○법에 의한 규제 : 해당 없음'처럼 법령 단위 줄이면 산안법·화관법·화평법 행의 항목 코드를 비운다.
    법령 하나에 대한 문장이라 특정 항목이 아니다 (골드 S001·S003). 위험물·폐기물은 골드도 코드를 둔다."""
    law = _law_of(row)
    m = _LAW_LEVEL.search(getattr(lines_by_id.get(row.get("line")), "text", "") or "")
    v = (m["v"] if m else "").strip()
    if law in ("OSH", "CCA", "KREACH") and m and (not v or status_word(v)[0] or _word_key(v) in ("해당", "비해당", "해당됨")):
        return {**row, "law": law, "item_code": None}
    return row


def _section_names_component(rows: list[dict], component: dict, lines_by_id: dict[str, Line]) -> bool:
    """행들의 근거 줄이 걸친 범위(처음~끝 줄)에 성분 이름·영문명·CAS·이명이 한 번이라도 나오는가.
    15항이 법령 단위로만 적혀 성분이 나오지 않으면 그 값은 제품 전체 값이다 (R10, 골드 S001·S003 MIX / S014·S016 성분)."""
    ids = list(lines_by_id)
    at = sorted({ids.index(r["line"]) for r in rows if r.get("line") in lines_by_id})
    if not at:
        return True
    text = _norm(" ".join(lines_by_id[i].text for i in ids[at[0]:at[-1] + 1]))
    names = [component.get("name"), component.get("name_en"), component.get("cas_no"), *(component.get("synonyms") or [])]
    return any(_norm(n) and _norm(n) in text for n in names)


_HEAD = r"^\s*(?:[○●ο◦•·\-*o]\s*|\d+\s*[.)]\s*|[가-하]\s*[.)]\s*)?\s*"
_HEADS = {
    "toxicity": [("TX_SKIN_SENS", r"피부\s*과민"), ("TX_RESP_SENS", r"호흡기\s*과민"), ("TX_SKIN", r"피부\s*(?:부식|자극)"),
                 ("TX_EYE", r"(?:심한\s*)?눈\s*(?:손상|자극)"), ("TX_CARC", r"발암"), ("TX_MUTA", r"생식\s*세포|변이원"),
                 ("TX_REPRO", r"생식\s*독성"), ("TX_STOT_SE", r"(?:특정\s*)?표적\s*장기.{0,12}?(?:1\s*회|단회)"),
                 ("TX_STOT_RE", r"(?:특정\s*)?표적\s*장기.{0,12}?반복"), ("TX_ASP", r"흡인"),
                 ("TX_ORAL", r"경구"), ("TX_DERMAL", r"경피"), ("TX_INHAL", r"흡입")],
    "ecotox": [("ECO_FISH", r"어류"), ("ECO_CRUST", r"갑각류|물벼룩"), ("ECO_ALGAE", r"조류"), ("ECO_PERSIST", r"잔류성|(?<!생)분해성"),
               ("ECO_BIOACC", r"생물\s*농축|농축성"), ("ECO_SOIL", r"토양\s*이동"), ("ECO_OZONE", r"오존"),
               ("ECO_OTHER", r"기타\s*유해\s*영향")]}
_HEAD_TABLE = {11: "toxicity", 12: "ecotox"}
_CMR_ENDPOINT = {"발암성": "TX_CARC", "생식세포변이원성": "TX_MUTA", "생식독성": "TX_REPRO"}
_HEAD_TAIL = re.compile(r"^[^\s:：|]*(?:\s*(?:독성|물질|또는\s*\S*\s*자극성|\([^)]*\)|노출\)|정보))*\s*[:：|]?\s*")


def _heading(table: str, text: str) -> tuple[str, str] | None:
    """원문 줄이 독성·생태 항목명으로 시작하면 (항목 코드, 이름 뒤 값 글자). '생분해성'은 농축성 아래라 보지 않는다."""
    for code, pat in _HEADS[table]:
        if m := re.match(_HEAD + f"(?:{pat})", text or ""):
            if code == "ECO_PERSIST" and re.match(_HEAD + r"생분해", text):
                return None
            rest = text[m.end():]
            return code, rest[_HEAD_TAIL.match(rest).end():].strip(" -|:：")
    return None


def extras_to_rows(extras: list[tuple[int, dict]], lines_by_id: dict[str, Line]
                   ) -> tuple[dict[str, list[tuple[int, dict]]], list[tuple[int, dict]]]:
    """11·12항 extras 가운데 원문 줄이 독성·생태 항목명으로 시작하고 값이 있는 것을 그 표의 서술 행으로 옮긴다.
    모델이 'o 피부 과민성 알레르기성 …' 같은 서술 행을 extras로 보냈다 (개발 골드 10건 기준 실행마다 독성 8.4·생태 9.5행).
    제목이 성분인 extras('- 이소부텐 : 자료없음')는 부모 줄의 항목명을 쓴다. 값이 상태어 하나면 그 상태(지표는 비워 둔다),
    아니면 값있음·결과기술·q 없음(골드 서술 행 표기). 숫자가 든 값은 지표를 정할 수 없어 옮기지 않는다.
    생태는 상태어 값만 옮긴다. '나. 잔류성 및 분해성'처럼 여러 낱말 제목의 뒷말을 값으로 읽어 틀린 행이 더 많았다
    (실행 8개 재채점: 상태어 아닌 값까지 옮기면 맞는 행 3.8 대 틀린 행 20.4/회)."""
    parents = line_parents(list(lines_by_id.values()))
    moved: dict[str, list[tuple[int, dict]]] = {"toxicity": [], "ecotox": []}
    left = []
    for no, r in extras:
        table, line = _HEAD_TABLE.get(no), lines_by_id.get(r.get("line"))
        got = _heading(table, line.text) if table and line else None
        stmts = " ".join(s.get("value") or "" for s in r.get("statements") or []).strip()
        if table and line and got is None and (r.get("comp_name") or r.get("comp_cas")):
            up = next((h for h in (_heading(table, x.text) for x in parents.get(line.id, [])) if h), None)
            after = line.text.split(":", 1)[1] if ":" in line.text else ""
            got = (up[0], after.strip()) if up else None
        value = (got[1] if got else "") or stmts
        if not got or not value or re.search(r"\d", value):
            left.append((no, r))
            continue
        status = status_word(value)[0]
        if table == "ecotox" and not status:
            left.append((no, r))
            continue
        row = {"comp_name": r.get("comp_name"), "comp_cas": r.get("comp_cas"), "endpoint": got[0], "line": line.id}
        if status:
            row.update(descriptor=None, q={"raw": value}, status=status, statements=[])
        else:
            row.update(descriptor="결과기술", q=None, status="값있음", statements=[{"value": value, "line": line.id}])
        moved[table].append((no, row))
    return moved, left


_STANDARD_LINE = re.compile(r"^(?P<s>국내|ACGIH|생물학적|OSHA|NIOSH|EU)\s*(?:규정|노출\s*기준)?\s*[:：|]?\s*(?P<v>.+)$")


def standard_status_rows(rows: list[dict], span: list[str], lines_by_id: dict[str, Line]) -> list[dict]:
    """8항 범위(span 줄들의 처음~끝)의 '기준 이름 : 상태어' 줄을 가리키는 노출기준 행이 없으면 더할 MIX 행들.
    종류는 TWA, 생물학적은 BEI (골드 값 없는 노출기준 40행 모두). 모델은 M002 'ο 국내규정 : 자료없음' 등 6줄을
    extras 한 덩어리로 묶었다."""
    ids = list(lines_by_id)
    at = sorted(ids.index(x) for x in span if x in lines_by_id)
    if not at:
        return []
    cited = {r.get("line") for r in rows}
    new = []
    for lid in ids[at[0]:at[-1] + 1]:
        m = _STANDARD_LINE.match(_strip_bullet(lines_by_id[lid].text))
        if m and lid not in cited and (status := status_word(m["v"].strip())[0]):
            new.append({"comp_name": None, "comp_cas": None, "standard": m["s"],
                        "limit_type": "BEI" if m["s"] == "생물학적" else "TWA", "q": {"raw": status}, "line": lid})
    return new


_KOW = re.compile(r"log\s*[KP]\s*o\s*w", re.IGNORECASE)


def fix_eco_descriptor(row: dict, lines_by_id: dict[str, Line]) -> dict:
    """생태 행의 지표. 값(숫자)이 없으면 비워 A 규칙(어류·갑각류·조류·토양 결과기술, 잔류성 분해율, 농축성 BCF→분해율)에
    맡긴다 — 골드 표기와 같다. 모델은 '- 트랜스 2 부텐 : 자료없음'에 LC50·EC50을 붙였다 (M004).
    숫자 행인데 근거 줄에 log Kow·log Pow가 있으면 logKow (골드 21행. 모델은 결과기술로 적었다)."""
    q = row.get("q") or {}
    if all(q.get(k) is None for k in ("value", "lower", "upper")):
        return {**row, "descriptor": None}
    text = getattr(lines_by_id.get(row.get("line")), "text", "") or ""
    if row.get("descriptor") in (None, "결과기술", "기타") and _KOW.search(text):
        return {**row, "descriptor": "logKow"}
    return row


_STANDARD_HEAD = re.compile(r"^\s*(국내|ACGIH|생물학적|OSHA|NIOSH|EU)")


def _span_ids(span: list[str], lines_by_id: dict[str, Line]) -> list[str]:
    ids = list(lines_by_id)
    at = sorted(ids.index(x) for x in span if x in lines_by_id)
    return ids[at[0]:at[-1] + 1] if at else []


def table_status_rows(rows: list[dict], span: list[str], lines_by_id: dict[str, Line]) -> list[dict]:
    """8항 표(머리글 '구성성분 | 국내규정 | ACGIH규정 | 생물학적 노출기준')의 성분 줄 칸이 상태어면, 그 성분 × 기준 행이 없을 때
    더할 행들. 종류는 TWA, 생물학적은 BEI (골드 M004 18행. 모델은 자료없음 칸을 뺐다). 값 칸은 모델에 맡긴다.
    쪽이 바뀌어 머리글이 반복돼도 같은 표로 본다."""
    have = {(r.get("line"), r.get("standard")) for r in rows} | {(_norm(r.get("comp_name")), r.get("standard")) for r in rows}
    header, new = None, []
    for lid in _span_ids(span, lines_by_id):
        cells = [c.strip() for c in lines_by_id[lid].text.split("|")]
        if len(cells) >= 3 and all(_STANDARD_HEAD.match(c) for c in cells[1:]):
            header = [_STANDARD_HEAD.match(c)[1] for c in cells[1:]]
            continue
        if not header or len(cells) != len(header) + 1 or not cells[0] or _STANDARD_HEAD.match(cells[0]):
            continue
        for std, cell in zip(header, cells[1:]):
            status = status_word(cell)[0]
            if status and (lid, std) not in have and (_norm(cells[0]), std) not in have:
                new.append({"comp_name": cells[0], "comp_cas": None, "standard": std,
                            "limit_type": "BEI" if std == "생물학적" else "TWA", "q": {"raw": cell}, "line": lid})
    return new


def heading_status_rows(table: str, rows: list[dict], span: list[str], lines_by_id: dict[str, Line],
                        components: list[dict]) -> list[dict]:
    """11·12항 '- 성분 : 상태어' 줄이 항목 소제목(● 어류 등) 아래 있고 그 행이 없으면 더할 서술 행들. 위로 올라가며 성분 줄과
    항목 소제목이 아닌 줄(쪽 머리글·쪽 번호)을 건너뛰고 처음 만나는 항목 소제목의 코드를 쓴다 (골드 M004 '● 조류' 아래
    '- 트랜스 2 부텐 : 자료없음'. 모델은 이런 줄 일부를 뺐다). 값이 상태어가 아닌 줄은 모델에 맡긴다."""
    keys = {_norm(x): c for c in components for x in (c.get("name"), c.get("name_en"), c.get("cas_no"), *(c.get("synonyms") or []))
            if _norm(x)}
    ids = _span_ids(span, lines_by_id)
    have = {(r.get("line"), r.get("endpoint")) for r in rows}
    new = []
    for i, lid in enumerate(ids):
        text = _strip_bullet(lines_by_id[lid].text)
        name, _, value = text.partition(":")
        if not value or not _any_component(name, keys) or not (status := status_word(value.strip())[0]):
            continue
        code = None
        for up in reversed(ids[max(0, i - 15):i]):
            up_text = lines_by_id[up].text
            if (got := _heading(table, up_text)) is not None:
                code = got[0]
                break
            if not _any_component(up_text, keys) and re.match(r"^\s*(?:[가-하]\s*[.)]|\d+\s*[.)])", up_text):
                break                        # 다른 큰 제목(가. 나. …)을 넘지 않는다
        if code and (lid, code) not in have:
            have.add((lid, code))
            new.append({"comp_name": name.strip(), "comp_cas": None, "endpoint": code, "descriptor": None,
                        "q": {"raw": status}, "status": status, "statements": [], "line": lid})
    return new


def collapse_unnamed(rows: list[dict], components: list[dict], lines_by_id: dict[str, Line]) -> list[dict]:
    """근거 줄·부모 줄에 성분 이름·CAS가 없는데 성분만 다르고 나머지가 같은 행이 둘 이상이면 MIX 한 행으로 모은다.
    골드는 성분 없는 줄의 독성·CMR·생태 행을 모두 MIX 한 행으로 적는다 (M002 'ο 발암성 : 자료없음'을 모델이 성분마다 복제).
    부모 줄이 성분을 가리키면('- 부탄 : …' 아래 '· OSHA : 해당없음') 성분별 행이 맞으므로 그대로 둔다."""
    if len(components) < 2:
        return rows
    parents = line_parents(list(lines_by_id.values()))
    keys = {_norm(x): c for c in components for x in (c.get("name"), c.get("name_en"), c.get("cas_no"), *(c.get("synonyms") or []))
            if _norm(x)}
    def named(line_id: str | None) -> bool:
        line = lines_by_id.get(line_id)
        return line is None or any(_any_component(x.text, keys) for x in [line, *parents.get(line.id, [])])
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(json.dumps({k: v for k, v in r.items() if k != "comp_ref"}, ensure_ascii=False, sort_keys=True),
                          []).append(i)
    drop, mix = set(), set()
    for idx in groups.values():
        if len({rows[i]["comp_ref"] for i in idx} - {"MIX"}) >= 2 and not named(rows[idx[0]].get("line")):
            mix.add(idx[0])
            drop.update(idx[1:])
    return [{**r, "comp_ref": "MIX"} if i in mix else r for i, r in enumerate(rows) if i not in drop]


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
            if no in EXTRACT_SECTIONS:     # 추출 대상이 아닌 항은 처음부터 부르지 않으므로 없어도 문제가 아니다
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
    # 1-2. 폭발 범위 상한/하한 한 줄은 UEL·LEL 두 행으로 (모델 표기가 실행마다 달랐다)
    phys = split_flammability(phys, lines_by_id)   # 빈 값은 뒤에서 source_rules.fill_no_value가 채운다
    rows["physchem"], rows["extras"] = phys, extras
    # 1-2-1. 기관이 빈 CMR 행은 기관 분류가 아니라 11항 독성 내용이다. 독성 행으로 옮긴다
    #        (골드 S013 'Methane : 음성 …' → TX_MUTA, '자료없음' → TX_CARC. 골드 CMR 61행은 모두 기관이 있다)
    have = {(r.get("line"), r.get("endpoint")) for _, r in rows["toxicity"]}
    for no, r in rows["cmr"]:
        code = _CMR_ENDPOINT.get(_word_key(r.get("hazard") or ""))
        status = r.get("status") or ("값있음" if r.get("note") else None)
        if r.get("agency") or not code or not status or (r.get("line"), code) in have:
            continue
        have.add((r.get("line"), code))
        rows["toxicity"].append((no, {"comp_name": r.get("comp_name"), "comp_cas": r.get("comp_cas"), "endpoint": code,
                                      "descriptor": None, "q": {"raw": status} if status in _NO_VALUE else None,
                                      "status": status, "line": r.get("line"),
                                      "statements": [{"value": r["note"], "line": r.get("line")}] if r.get("note") else []}))
    # 1-3. 8항 '기준 이름 : 상태어' 줄을 가리키는 노출기준 행이 없으면 더한다 (모델이 extras로 묶었다)
    span8 = [x for no, r in [*rows["exposure_limits"], *rows["extras"], *rows["narratives"]] if no == 8
             for v in (r.get("line"), r.get("start"), r.get("end")) if v for x in re.findall(r"p\d+:L\d+", v)]
    rows["exposure_limits"] += [(8, r) for r in standard_status_rows([r for _, r in rows["exposure_limits"]], span8, lines_by_id)]
    rows["exposure_limits"] += [(8, r) for r in table_status_rows([r for _, r in rows["exposure_limits"]], span8, lines_by_id)]
    # 1-4. 11·12항 extras 중 항목명으로 시작하는 서술 줄은 독성·생태 행으로. 모델이 같은 줄에 같은 항목 행을 냈으면 두지 않는다
    moved, rows["extras"] = extras_to_rows(rows["extras"], lines_by_id)
    for key, new in moved.items():
        have = {(r.get("line"), r.get("endpoint")) for _, r in rows[key]}
        new = [(no, r) for no, r in new if (r["line"], r["endpoint"]) not in have]
        if new:
            rows[key] = sorted(rows[key] + new, key=lambda p: pos.get(p[1].get("line"), len(pos)))

    # 서술 구간(양 끝 포함 줄 위치)을 항마다 모은다. extras 거르기에 쓰므로 펼치기 전에 끝낸다 (ADR-022).
    # narrative()가 문장을 만드는 구간과 같다: 두 끝이 원문에 있고 start <= end.
    spans: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for no, r in rows["narratives"]:
        start, end = r.get("start"), r.get("end")
        if start in pos and end in pos and pos[start] <= pos[end]:
            spans[no].append((pos[start], pos[end]))

    # 2. TO21 키 순서대로 펼친다. 성분은 다른 행의 comp_ref가 가리키므로 먼저 만든다.
    # 성분표의 합계 행('Total | 100%')과 이름·CAS가 모두 빈 행은 성분이 아니다. 남기면 단일 성분 문서가 두 성분이 된다 (S001)
    rows["components"] = [(no, r) for no, r in rows["components"]
                          if r.get("cas_no") or (r.get("name") and not _TOTAL.match(r["name"]))]
    components = _shape(props["components"], [r for _, r in rows["components"]], lines_by_id)
    # 12항 소제목 아래 '- 성분 : 상태어' 줄에 행이 없으면 더한다 (모델이 뺀 값 없는 행, 골드 M004).
    # 11항에도 쓰면 급성은 오르고 기타 독성은 내려 종합이 같아(실행 10개 재채점) 12항만 쓴다
    for no, key in ((12, "ecotox"),):
        span = [x for t_ in rows.values() for n_, r in t_ if n_ == no
                for v in (r.get("line"), r.get("start"), r.get("end")) if isinstance(v, str) for x in re.findall(r"p\d+:L\d+", v)]
        rows[key] += [(no, r) for r in heading_status_rows(key, [r for _, r in rows[key]], span, lines_by_id, components)]
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
        if key == "cmr":       # 기관이 빈 행은 제품·항목 줄(PRODUCT : 분류되지않음 등)이라 기관 분류가 아니다 (골드 CMR 61행 모두 기관 있음)
            pairs = [(no, r) for no, r in pairs if r.get("agency")]
            pairs = [(no, {**r, "class": _GROUP.sub("", r["class"])}            # 등급은 원문 표기대로 (골드 M013 '2B' / S016 'Group 1')
                      if r.get("class") and _GROUP.match(r["class"])
                      and "group" not in getattr(lines_by_id.get(r.get("line")), "text", "group").lower() else r)
                     for no, r in pairs]
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
            if key in ("toxicity", "cmr", "ecotox"):
                src = collapse_unnamed(src, components, lines_by_id)
            if key in _SINGLE_COMP_KEYS and len(components) == 1:
                if key == "regulations" and not _section_names_component(src, components[0], lines_by_id):
                    src = [{**r, "comp_ref": "MIX"} for r in src]   # 15항에 성분이 안 나오면 제품 값 (R10, 골드 S001·S003)
                else:
                    src = [{**r, "comp_ref": str(components[0]["seq"])}
                           if r["comp_ref"] == "MIX" and _law_of(r) not in _PRODUCT_LAWS else r for r in src]
        if key == "ecotox":
            src = [fix_eco_descriptor(r, lines_by_id) for r in src]
        if {"q", "text_value"} <= _resolve(node["items"]).get("properties", {}).keys():
            src = [status_to_q(r) for r in src]
        if key == "physchem":
            src = fill_no_value(src, lines_by_id)        # 근거 줄의 '자료없음' 등으로 빈 값 (ADR-029)
        if key == "regulations":
            recode_regulations(src, lines_by_id, components)
            src = src + add_missing_items(src, lines_by_id)      # 모델 행 순서는 그대로 두고 뒤에 더한다
            src = src + dg_row_from_table(src, [r for _, r in rows.get("dangerous_goods", [])])
            src = [_law_level_item(r, lines_by_id) for r in src]
            if src and not any(_law_of(r) == "KREACH" for r in src):   # R18: 화평법 항목이 없는 문서는 미기재 한 행 (골드 6건)
                src.append({"law": "KREACH", "item_code": None, "applicable": "미기재", "comp_ref": "MIX"})
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
                if q and all(q.get(k) is None for k in ("value", "lower", "upper")) and (re.search(r"단순\s*질식", q.get("raw") or "")
                                                                                 or _word_key(q.get("raw") or "") == "없음"):
                    q["status"] = "해당없음"            # 단순 질식제·'없음': 수치 기준이 없다 (골드 S003·S013, 실버 S001·S003)
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
