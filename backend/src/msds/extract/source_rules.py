"""원문 줄로 확인하는 고침 (B, ADR-029).

펼친 TO21 msds 항목을 문서의 원문 줄과 맞춰 본다. 원문 글자로 확인되는 값만 고친다.
expand.to_to21이 MSDS마다 expand_msds 뒤, A의 apply_conventions 앞에 부른다.
규칙은 글의 꼴로만 정한다. 문서 번호로 나누지 않는다.
- H·P 코드: 문서 글에 그 종류의 코드 꼴이 하나도 없으면 모델이 쓴 코드를 비운다. 문장은 둔다.
  2항 그림(이미지 입력)에서만 읽은 코드를 지우지 않으려고, 글에 코드가 전혀 없는 문서만 고친다.
- 개정 횟수: '개정 횟수 … : N' 줄로 meta.revision_no를 정한다. 'N-N'이면 비운다.
- 메타 값 없음: meta의 글자 칸이 자료없음·해당없음·미기재(공백 무시)이면 비운다.
- 메타 원문 확인: 제출번호는 형식(^AA\d{5}-\d{10}$)에 맞고 원문에 있을 때만, 첫 작성일·최종 개정일은 원문에 적혀 있을 때만 남긴다.
- 전화번호: 연락처가 원문에 그대로 없고, 숫자가 같은 원문 조각이 있으면 그 조각으로 바꾼다.
- 유해성 분류: MSDS 한 건인 문서에서 모델이 hazard.classes를 비웠으면 2항 분류 줄('- 인화성 액체 : 구분2')을
  명세서 5-1 코드표(없으면 13 매핑 시트의 '이름 : 구분 N' 글)로 읽어 채운다. 모델이 쓴 분류는 건드리지 않는다.
- 15항 기준농도: 규제 행의 근거 줄에 적힌 'N% 이상'·'N wt% 이상'으로 threshold를 채우거나 바로잡는다(fill_thresholds).
  expand_msds가 펼치기 전(행에 line이 있을 때) 부른다. 법령 표의 값은 쓰지 않는다. 원문에 적힌 값만 쓴다.
"""
from __future__ import annotations

import re
from functools import lru_cache

from msds.extract.inputs import Line
from msds.extract.rows import _has_number, parse_qm
from msds.extract.section_prompts import _workbook

_NO_VALUE = ("자료없음", "해당없음", "미기재")      # 값 없는 칸 (expand._NO_VALUE와 같다)
# 앞뒤가 다른 영문·숫자가 아닌 코드 꼴. H코드는 TO21 접미 문자(H360FD, H361d)까지 코드로 본다.
_CODE_FORMS = {
    "h_statements": ("H", re.compile(r"(?<![A-Za-z0-9])(?:EU)?H\d{3}[A-Za-z]{0,2}(?![A-Za-z0-9])")),
    "p_statements": ("P", re.compile(r"(?<![A-Za-z0-9])P\d{3}(?![A-Za-z0-9])")),
}
_REVISION = re.compile(r"개정\s*횟수[^:：]*[:：](?P<value>.*)$")
_REVISION_NO = re.compile(r"(\d+)\s*회?")
_REVISION_PAIR = re.compile(r"\d+\s*-\s*\d+")
_PHONE_GAP = r"[\s\-()]*"     # 전화번호 숫자 사이에 올 수 있는 글자
_PHONE_MIN = 7                # 원문 조각의 최소 글자 수
# 유해성 분류: 공백을 지운 글에서 찾는 구간 머리와 끝, 줄 안의 '이름 : 구분N' 항목
_CLASS_HEAD = re.compile(r"유해성?[·ㆍ]?위험성분류")
_CLASS_END = re.compile(r"그림문자|신호어|경고표지|예방조치")
_CLASS_ITEM = re.compile(r"(?P<name>(?:[^:：,|()]|\([^()]*\))+?)\s*[:：]\s*구분\s*(?P<cat>\d+[A-Za-z]?)(?![0-9A-Za-z])")
_CLASS_BULLET = re.compile(r"^(?:\s|[-–•○●◦■□▪*ο]|[가-하][.)]|\(?\d{1,2}[.)])+")   # ο: ○를 그리스 글자로 읽은 것
_CLASS_ALIASES = {"만성수생환경유해성": "ENV_AQ_CHRONIC", "급성수생환경유해성": "ENV_AQ_ACUTE"}  # 5-1은 '수생환경 유해성(만성)'
_SOURCE_MAX = 200             # TO21 evidence.source_text: 200자 이내
# 15항 기준농도 조각: 'N% 이상'·'N wt% 이상'. 앞이 숫자·점이면 다른 수의 끝이라 보지 않는다('10.1%'의 '1%')
_THRESHOLD = re.compile(r"(?<![\d.])(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>wt\s*%|%)\s*이상")
# 새 항목을 여는 줄 머리: 글머리 기호, 원 숫자, '1.'·'1)'·'가.'·'(가)'. 이런 다음 줄은 다른 행의 줄이라 잇지 않는다
_NEW_ITEM = re.compile(r"^(?:[-–•·○●◦■□▪*ο]|[①-⑳]|\(?\d{1,2}[.)](?!\d)|\(?[가나다라마바사아자차카타파하][.)])")


def _clear_codes(item: dict, text: str) -> list[str]:
    changes = []
    for key, (label, form) in _CODE_FORMS.items():
        rows = [s for s in item["hazard"][key] if s.get("code") is not None]
        if rows and not form.search(text):
            for s in rows:
                s["code"] = None
            changes.append(f"{label} 코드 {len(rows)}개 비움: 문서 글에 {label} 코드 꼴이 없음")
    return changes


def _revision_no(item: dict, lines: list[Line]) -> list[str]:
    line, m = next(((l, m) for l in lines if (m := _REVISION.search(l.text))), (None, None))
    if m is None:
        return []
    value = m["value"].split(",")[0].strip()
    if n := _REVISION_NO.fullmatch(value):
        new = int(n.group(1))
    elif _REVISION_PAIR.fullmatch(value):
        new = None
    else:
        return []
    old = item["meta"]["revision_no"]
    if old == new:
        return []
    item["meta"]["revision_no"] = new
    return [f"meta.revision_no {old!r} → {new!r} ({line.id})"]


def _meta_no_value(item: dict) -> list[str]:
    changes = []
    for k, v in item["meta"].items():
        if isinstance(v, str) and re.sub(r"\s+", "", v) in _NO_VALUE:
            item["meta"][k] = None
            changes.append(f"meta.{k} {v!r} → None")
    return changes


_MSDS_NO = re.compile(r"^AA\d{5}-\d{10}$")         # 명세서 1_항목정의 meta.msds_no 형식 (스키마 pattern)
_DATE_FIELDS = ("first_issue_date", "last_revision_date")


def _date_in(value: str, lines: list[Line]) -> bool:
    """'YYYY-MM-DD'가 원문에 연·월·일(또는 일·월·연) 순서로 적혀 있는지. '2019. 3. 8', '2010년 06월 21일', '21/12/2017',
    '20230218' 꼴을 본다."""
    y, m, d = value.split("-")
    m, d = int(m), int(d)
    forms = (rf"{y}\D{{1,4}}0?{m}\D{{1,4}}0?{d}(?!\d)", rf"(?<!\d)0?{d}\D{{1,4}}0?{m}\D{{1,4}}{y}", rf"{y}{m:02d}{d:02d}")
    return any(re.search(f, l.text) for l in lines for f in forms)


def _meta_in_source(item: dict, lines: list[Line]) -> list[str]:
    """제출번호는 형식(^AA\\d{5}-\\d{10}$)에 맞고 원문에 있을 때만, 날짜는 원문에 적혀 있을 때만 남긴다.
    모델이 명세서 예시(AA00000-…)나 회사 약칭을 제출번호로, 없는 날짜를 개정일로 쓴 일이 있었다(11/01 실행)."""
    changes, meta = [], item["meta"]
    no = meta.get("msds_no")
    alnum = lambda s: re.sub(r"[^0-9A-Za-z]", "", s).upper()      # 원문의 공백·여러 하이픈 꼴은 무시한다
    if no and not (_MSDS_NO.match(no) and alnum(no) in alnum("".join(l.text for l in lines))):
        meta["msds_no"] = None
        changes.append(f"meta.msds_no {no!r} → None (형식 또는 원문 없음)")
    for k in _DATE_FIELDS:
        v = meta.get(k)
        if v and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) and not _date_in(v, lines):
            meta[k] = None
            changes.append(f"meta.{k} {v!r} → None (원문 없음)")
    return changes


def _phone_fragment(value: str, lines: list[Line]) -> str | None:
    """숫자만 남기면 value와 같은 원문 조각(숫자로 시작·끝나고 사이에 숫자·'-'·공백·괄호만, 7자 이상)."""
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    form = re.compile(r"(?<!\d)" + _PHONE_GAP.join(digits) + r"(?!\d)")
    for line in lines:
        for m in form.finditer(line.text):
            if len(m.group(0).strip()) >= _PHONE_MIN:
                return m.group(0).strip()
    return None


def _phones(item: dict, lines: list[Line], text: str) -> list[str]:
    changes = []
    for company in item["companies"]:
        for c in company.get("contacts") or []:
            value = c.get("value")
            if not isinstance(value, str) or value in text:
                continue
            if (frag := _phone_fragment(value, lines)) is not None:
                c["value"] = frag
                changes.append(f"연락처 {value!r} → {frag!r}")
    return changes


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("：", ":").replace("ㆍ", "·")


@lru_cache(maxsize=1)
def _class_tables() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """명세서에서 (코드 → 구분, 5-1 이름 → 코드, 13 시트 '이름:구분N' → 코드). 이름은 공백을 지운 글이다."""
    wb = _workbook()
    groups, by_name, by_text = {}, {}, {}
    for group, code, name in wb["5-1_유해성분류"].iter_rows(min_col=1, max_col=3, values_only=True):
        if group in ("물리적", "건강", "환경") and code and name:
            groups[code] = group
            by_name[_compact(str(name).split(" — ")[0])] = code
    for code, *_, text, _note in wb["13_TO21DB매핑"].iter_rows(min_col=1, max_col=7, values_only=True):
        if code in groups and isinstance(text, str) and ":" in text:
            by_text[_compact(text)] = code
    return groups, by_name, by_text


def _class_code(name: str, category: str) -> str | None:
    _, by_name, by_text = _class_tables()
    key = _compact(name)
    return by_name.get(key) or _CLASS_ALIASES.get(key) or by_text.get(f"{key}:구분{category}")


def _class_span(lines: list[Line]) -> list[Line]:
    """'유해성·위험성 분류' 머리 줄부터 그림문자·신호어·경고표지·예방조치 줄 앞까지."""
    start = next((i for i, l in enumerate(lines) if _CLASS_HEAD.search(_compact(l.text))), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines)) if _CLASS_END.search(_compact(lines[i].text))), len(lines))
    return lines[start:end]


def _classes(item: dict, lines: list[Line]) -> list[str]:
    hazard = item["hazard"]
    if hazard.get("classes"):
        return []
    groups = _class_tables()[0]
    rows, found = [], []
    for line in _class_span(lines):
        for m in _CLASS_ITEM.finditer(line.text):
            name = _CLASS_BULLET.sub("", m["name"]).strip()
            category = m["cat"]
            code = _class_code(name, category)
            if code is None:
                continue
            rows.append({"seq": len(rows) + 1, "group": groups[code], "class_code": code, "category": category,
                         "route_form": None, "effect": None, "target_organs": [],
                         "raw": name + m.group(0)[len(m["name"]):]})
            found.append(line)
    if not rows:
        return []
    hazard["classes"] = rows
    item["evidence"] += [{"field": f"hazard.classes[{i}]", "page": line.page, "bbox": None,
                          "source_text": line.text[:_SOURCE_MAX], "confidence": None, "method": "규칙",
                          "needs_review": True} for i, line in enumerate(found)]
    return [f"hazard.classes {len(rows)}행을 원문 분류 줄로 채움 ({found[0].id}~{found[-1].id})"]


def _after_item(item_raw: str | None, text: str) -> re.Match | None:
    """item_raw(공백 무시) 바로 뒤 괄호 '(N% 이상)'의 조각. 예: '관리대상 유해물질(0.1% 이상)' → '0.1% 이상'."""
    chars = [re.escape(c) for c in re.sub(r"\s+", "", item_raw or "")]
    if not chars:
        return None
    for m in re.finditer(r"\s*".join(chars) + r"\s*\(\s*", text):
        if (f := _THRESHOLD.match(text, m.end())) and re.match(r"\s*\)", text[f.end():]):
            return f
    return None


def _threshold_qm(f: re.Match) -> dict:
    """조각 → QM. 값은 parse_qm('<N> <단위> 이상'), raw는 원문 조각."""
    unit = re.sub(r"\s+", "", f["unit"])
    return {**parse_qm(f"{f['n']} {unit} 이상"), "raw": f.group(0)}


def fill_thresholds(rows: list[dict], lines_by_id: dict[str, Line]) -> list[dict]:
    """15항 규제 행(아직 line이 있는 중간 형식 행)의 threshold를 근거 줄로 채우거나 바로잡은 새 목록.
    근거 글은 행 line의 줄과 바로 다음 줄('(1%' / '이상)'처럼 끊긴 경우)을 공백 하나로 이은 글이다.
    다음 줄이 글머리('- ', '●', '가.' 등)로 시작하면 다른 성분·항목의 줄이라 잇지 않는다.
    - 채우기: threshold에 숫자가 없으면 ① item_raw 바로 뒤의 '(N% 이상)', 없으면 ② 근거 글에 하나뿐인 'N% 이상'.
    - 바로잡기: threshold의 숫자가 하나이고 근거 글에 같은 숫자의 'N% 이상'이 있으면(① 조각 먼저) 그 조각으로 바꾼다.
      부등호는 >=, 단위는 원문 그대로(% 또는 wt%)가 된다. 범위(숫자 둘)와 근거 글에 없는 숫자는 그대로 둔다.
    - 근거 줄이 없거나 원문에 없는 줄 번호인 행은 그대로 둔다. 넘겨받은 행은 바꾸지 않는다."""
    ids = list(lines_by_id)
    pos = {lid: i for i, lid in enumerate(ids)}
    out = []
    for r in rows:
        at = pos.get(r.get("line"))
        if at is None:
            out.append(r)
            continue
        own, *rest = (lines_by_id[lid].text.strip() for lid in ids[at:at + 2])
        text = " ".join([own, *(t for t in rest if not _NEW_ITEM.match(t))])
        found = list(_THRESHOLD.finditer(text))
        item = _after_item(r.get("item_raw"), text)
        q = r.get("threshold")
        if not _has_number(q):
            f = item or (found[0] if len(found) == 1 else None)
        else:
            nums = [q[k] for k in ("value", "lower", "upper") if q.get(k) is not None]
            same = [x for x in (item, *found) if x and len(nums) == 1 and float(x["n"]) == nums[0]]
            f = same[0] if same else None
        out.append({**r, "threshold": _threshold_qm(f)} if f else r)
    return out


def apply_source_rules(item: dict, lines: list[Line], single_msds: bool = True) -> list[str]:
    """펼친 TO21 msds 항목 하나를 원문 줄로 확인해 바로 고친다. 고친 내용(사람이 읽는 한 줄씩)을 돌려준다.
    lines는 문서 전체 줄이다. 유해성 분류 채우기는 MSDS가 한 건(single_msds)일 때만 한다."""
    text = "\n".join(l.text for l in lines)
    return (_clear_codes(item, text) + _revision_no(item, lines) + _meta_no_value(item) + _meta_in_source(item, lines)
            + _phones(item, lines, text) + (_classes(item, lines) if single_msds else []))
