"""항목별 중간 형식(모델 응답)을 TO21 v0.6 JSON으로 펼친다 (B, ADR-001·002·004).

파일을 읽거나 쓰지 않고 모델을 부르지 않는다. 모양은 TO21 스키마(msds_item_schema)를 따라 만든다.
- 스키마에 있는 칸은 모두 넣는다(없으면 null, 배열은 []). 스키마에 없는 중간 형식 칸(line, lines,
  comp_name, comp_cas, start, end)은 남지 않는다.
- 형식(pattern)이 정해진 칸의 빈 글자("")는 null로 둔다. 중간 형식에는 형식 조건이 없어 모델이 ""를 쓴다.
- seq, Q의 status·dp·note, comp_ref, 서술 문장, extras의 쪽·항 번호, 근거(evidence)는 코드가 채운다.
- 값 없는 행의 표기는 A의 규칙 함수(msds.common.conventions.apply)에 맡긴다.
- 15항 화평법 행은 값이 있는데 해당 여부가 비면 '해당'으로 채운다 (사용자 결정 10/29).
"""
from __future__ import annotations

import importlib
import importlib.util
import re
from collections import Counter, defaultdict

from msds.common.merge import DICTIONARY_VERSION, SCHEMA_VERSION, now_kst
from msds.common.schema import load_schema, msds_item_schema
from msds.extract.inputs import SECTION_NOS, Line, line_index
from msds.extract.section_specs import META_REVISION_FIELDS

_NO_VALUE = {"자료없음", "해당없음", "미기재"}
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_BULLET = re.compile(r"^\s*(?:[-–](?!\d)|[•·○●◦■□▪*]|[①-⑳]|\(?\d{1,2}\)|\d{1,2}\.(?!\d)"
                     r"|\(?[가나다라마바사아자차카타파하][.)])\s*")
_PIPE_LEAD = re.compile(r"^\|\s*")    # version9: 불릿 기호가 표 칸처럼 ' | '로 묶여 온다
_COLON = re.compile(r"[:：]")
_COMP_KEYS = ("comp_name", "comp_cas")
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


def fill_q(qm: dict | None) -> dict | None:
    """QM(모델이 쓴 숫자 묶음)에 status·dp·note를 더해 TO21 Q로 만든다."""
    if qm is None:
        return None
    q = {k: qm.get(k) for k in _defs()["Q"]["properties"]}
    raw = re.sub(r"\s+", "", q["raw"] or "")
    num = next((q[k] for k in ("value", "lower", "upper") if q[k] is not None), None)
    q["status"] = raw if raw in _NO_VALUE else ("값있음" if num is not None else None)
    q["dp"] = _dp(q["raw"], num)
    q["note"] = None
    return q


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


def link_components(rows: list[dict], components: list[dict]) -> list[dict]:
    """comp_name·comp_cas를 3항 성분의 seq(글자)인 comp_ref로 바꾼 새 행 목록. CAS 먼저, 다음 이름.
    둘 다 비었거나 어느 성분에도 안 맞으면 "MIX"."""
    by_cas = {_norm(c.get("cas_no")): c for c in components if _norm(c.get("cas_no"))}
    by_name: dict[str, dict] = {}
    for c in components:
        for n in (c.get("name"), c.get("name_en"), *(c.get("synonyms") or [])):
            if _norm(n):
                by_name.setdefault(_norm(n), c)
    out = []
    for r in rows:
        c = by_cas.get(_norm(r.get("comp_cas"))) or by_name.get(_norm(r.get("comp_name")))
        out.append({**{k: v for k, v in r.items() if k not in _COMP_KEYS},
                    "comp_ref": str(c["seq"]) if c else "MIX"})
    return out


# ── 15항 화평법 해당 여부 ──────────────────────────────

def _has_value(text: str | None) -> bool:
    t = re.sub(r"\s+", "", text or "")
    return bool(t) and t not in _NO_VALUE | {"비해당"}


def fill_kreach_applicable(regulations: list[dict]) -> None:
    """화평법(KREACH) 행에 값(value_raw 또는 threshold)이 있는데 해당 여부(applicable)가 비면 '해당'으로 채운다.
    값 없는 행과 다른 법령 행은 그대로 둔다 (사용자 결정 10/29, A-1 답의 참고: TO21 정답이 '해당')."""
    for r in regulations:
        if (r.get("law") == "KREACH" and r.get("applicable") is None
                and (_has_value(r.get("value_raw")) or _has_value((r.get("threshold") or {}).get("raw")))):
            r["applicable"] = "해당"


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

    # 서술 구간(양 끝 포함 줄 위치)을 항마다 모은다. extras 거르기에 쓰므로 펼치기 전에 끝낸다 (ADR-022).
    # narrative()가 문장을 만드는 구간과 같다: 두 끝이 원문에 있고 start <= end.
    spans: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for no, r in rows["narratives"]:
        start, end = r.get("start"), r.get("end")
        if start in pos and end in pos and pos[start] <= pos[end]:
            spans[no].append((pos[start], pos[end]))

    # 2. TO21 키 순서대로 펼친다. 성분은 다른 행의 comp_ref가 가리키므로 먼저 만든다.
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
            src = link_components(src, components)
            for i, ((no, r), linked) in enumerate(zip(pairs, src)):
                if linked["comp_ref"] == "MIX" and (_norm(r.get("comp_name")) or _norm(r.get("comp_cas"))):
                    problem(no, "unlinked_component", f"{key}[{i}]: {r.get('comp_name')} / {r.get('comp_cas')}")
        item[key] = components if key == "components" else _shape(node, src, lines_by_id)
        if key == "regulations":
            fill_kreach_applicable(item[key])
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
