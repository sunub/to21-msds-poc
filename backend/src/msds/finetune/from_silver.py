"""묶음 방식 실버·골드(완성 TO21 JSON) → 항목별 추출의 중간 형식 정답 (11/03 F).

팀원 실버(data/silver/<모델>/<문서>.json, 프롬프트 p6 묶음 방식)와 골드는 완성 TO21 문서다. 로컬 모델은 항마다
중간 형식(행마다 원문 줄 번호 line, 객체 칸마다 lines)을 쓰고 펼치기(expand)가 TO21로 바꾼다. 그래서 학습 정답을 만들려면
거꾸로 TO21 문서를 항별 중간 형식으로 되돌려야 한다.

되돌리는 법 (section_specs.response_schema(no)의 칸을 따라 간다)
- 칸: 중간 형식 스키마에 있는 칸만 옮긴다(seq·status·dp·note·evidence 등 코드가 채우는 칸은 뺀다).
  숫자 묶음은 QM 칸만, comp_ref는 3항 성분(seq)의 이름·CAS로(MIX면 비움), 서술 항목은 item_code·title_raw·start·end로,
  extras는 이 항의 것(section_no)만.
- 줄 번호: 근거(msds[].evidence의 field·page·source_text)의 원문 조각을 이 항 호출에 보내는 줄(section_lines)에서 찾는다.
  근거가 없으면 행의 원문 글(STMT text, 유해성 분류 raw, H·P 코드, 이름 등)로 찾는다.
  같은 글이 여러 줄에 있으면 근거의 쪽 → 같은 표의 앞 행보다 뒤인 줄 → 처음 줄 순으로 고른다(표의 행은 문서 순서다).
  여러 줄에 걸친 조각은 시작하는 줄을 쓴다. 글자가 조금 다르면(표 칸 구분, 기호) 비슷한 정도 0.88 이상인 한 줄만 쓴다.
  근거 조각이 '…'로 줄여 있으면 앞 조각으로, 표 칸 구분(' | ')이 있으면 긴 칸부터, 길면 앞 16글자로도 찾아본다.
- 이 항 호출이 볼 수 없는 값은 정답에서 뺀다(이 호출의 모델은 그 줄을 못 본다).
  근거가 이 항 줄 밖(예: 16항의 작성일·개정일, 다른 항의 문장)에서 찾아지는 행·칸, 근거 글이 하나도 없는 행
  (펼치기가 만드는 '미기재' 행 등)이 그렇다. 뺀 수는 notes에 남는다.
- 원문 글이 아니라 판단으로 정한 칸(분류 여부, 단일물질·혼합물, 유해성분 없음)은 근거를 못 찾으면 이 항의 첫 줄(항 제목)을 쓴다.
- 그 밖에 줄을 못 찾은 행·칸이 하나라도 있으면 그 항 전체를 쓰지 않는다(틀린 줄 번호나 빠진 행을 배우지 않게).
  이유는 problems에 남는다.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from msds.checks.source_match import normalize
from msds.extract.inputs import Line, section_lines
from msds.extract.section_specs import QM_FIELDS, load_specs, response_schema

_PUNCT = re.compile(r"[:：\-·•*●○◦■□◆◇▶▷►※ㆍ∙,;'\"“”‘’()\[\]{}<>〈〉「」『』]")
_FUZZY = 0.88          # 비슷한 정도(글자 비교) 하한
_WINDOW = 6            # 여러 줄에 걸친 조각을 찾을 때 이어 붙이는 줄 수
# 근거가 없을 때 행에서 찾을 글을 고르는 칸 순서
_PROBE_FIELDS = ("text", "raw", "title_raw", "item_raw", "class_raw", "code", "name", "cas_no", "comp_cas", "value",
                 "shipping_name", "un_no")


def norm(text) -> str:
    return _PUNCT.sub("", normalize(str(text or "")))


class LineFinder:
    """이 항 호출에 보내는 줄에서 원문 조각의 줄을 찾는다."""

    def __init__(self, lines: list[Line]):
        self.lines = lines
        self.norms = [norm(l.text) for l in lines]

    def _hits(self, t: str) -> list[int]:
        hits = [i for i, n in enumerate(self.norms) if t in n]
        if hits:
            return hits
        for i in range(len(self.norms)):                    # 여러 줄에 걸친 조각: i번 줄에서 시작해야 한다
            acc = self.norms[i]
            if not acc:
                continue
            for j in range(i + 1, min(i + _WINDOW, len(self.norms))):
                acc += self.norms[j]
                pos = acc.find(t)
                if pos != -1:
                    if pos < len(self.norms[i]):
                        hits.append(i)
                    break
        return hits

    @staticmethod
    def variants(text) -> list[str]:
        """찾아볼 조각: 전체 → '…' 앞 조각 → 표 칸(긴 것부터) → 앞 16글자. 정규화한 글."""
        raw = str(text or "")
        out = [norm(raw)]
        parts = [norm(x) for x in re.split(r"\.\.\.|…", raw)]
        if len(parts) > 1:
            out += [parts[0]] if len(parts[0]) >= 6 else [max(parts, key=len)]
        if "|" in raw:
            out += sorted((c for c in (norm(x) for x in raw.split("|")) if len(c) >= 6), key=len, reverse=True)
        if len(out[0]) >= 24:
            out.append(out[0][:16])
        return [v for v in dict.fromkeys(out) if len(v) >= 2]

    def find(self, text, page: int | None = None, after: int = -1) -> int | None:
        """줄 위치(self.lines의 번호). 못 찾으면 None."""
        tries = self.variants(text)
        if not tries:
            return None
        hits = []
        for v in tries:
            hits = self._hits(v)
            if hits:
                break
        t = tries[0]
        if not hits:
            scored = [(SequenceMatcher(None, t, n).ratio(), i) for i, n in enumerate(self.norms)
                      if n and 0.7 <= len(n) / len(t) <= 1.4]
            good = sorted((s, i) for s, i in scored if s >= _FUZZY)
            if not good or (len(good) > 1 and good[-1][0] == good[-2][0]):
                return None
            hits = [good[-1][1]]
        on_page = [i for i in hits if page is not None and self.lines[i].page == page] or hits
        later = [i for i in on_page if i >= after]
        return (later or on_page)[0]


# 행의 값 중 줄을 찾는 데 쓰지 않는 칸(코드·선택지라 원문 글과 다르다)
_CODE_FIELDS = {"line", "lines", "start", "end", "item_code", "endpoint", "prop_code", "law", "descriptor", "status",
                "applicable", "agency", "hazard", "group", "class_code", "type", "role", "mode", "standard", "limit_type",
                "system", "reason", "seq", "comp_ref", "detection", "evidence", "page", "section_no", "after_item"}


def row_values(value) -> list[str]:
    """행·칸에서 원문에 그대로 적혀 있을 만한 글: _PROBE_FIELDS 순서의 글 칸 → 숫자 묶음의 원문 표기 → 그 밖의 글 칸."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value[:1] if isinstance(v, str)]
    if not isinstance(value, dict):
        return []
    out = [value[k] for k in _PROBE_FIELDS if isinstance(value.get(k), str) and value.get(k)]
    for k, v in value.items():
        if k in _CODE_FIELDS:
            continue
        if isinstance(v, dict) and isinstance(v.get("raw"), str) and v.get("raw"):
            out.append(v["raw"])
        elif isinstance(v, str) and v and k not in _PROBE_FIELDS:
            out.append(v)
    return list(dict.fromkeys(out))


def _resolve(node: dict, defs: dict) -> tuple[dict, str | None]:
    """null 허용을 벗기고 $ref를 따라간 노드와 그 이름(QM·COND·STMT 등)."""
    name = None
    while True:
        if "anyOf" in node:
            node = next((b for b in node["anyOf"] if b.get("type") != "null"), node["anyOf"][0])
        elif "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[1]
            node = defs[name]
        else:
            return node, name


OUTSIDE, NO_ANCHOR = "OUTSIDE", "NO_ANCHOR"     # 이 항 줄 밖에서 찾음 / 찾을 글이 없음
# 원문 글이 아니라 판단으로 정하는 칸: 근거를 못 찾으면 이 항의 첫 줄을 쓴다
INFERRED = {"composition.type", "composition.no_hazardous_component", "hazard.classified"}


class _Ctx:
    def __init__(self, item: dict, finder: LineFinder, doc_finder: LineFinder, first_line: str | None):
        self.item = item
        self.finder = finder
        self.doc_finder = doc_finder
        self.first_line = first_line
        self.notes: list[str] = []
        self.evidence: dict[str, list[tuple[int | None, str]]] = {}
        for e in item.get("evidence") or []:
            if e.get("field") and e.get("source_text"):
                self.evidence.setdefault(e["field"], []).append((e.get("page"), e["source_text"]))
        self.components = {str(c.get("seq")): c for c in item.get("components") or [] if isinstance(c, dict)}
        self.cursor: dict[str, int] = {}
        self.problems: list[str] = []

    def anchors(self, path: str, value) -> list[tuple[int | None, str]]:
        """줄을 찾을 글 후보: 이 경로의 근거 → 행의 글(이름·원문 표기 등) → 이 경로 아래 칸의 근거.
        아래 칸의 근거(예: 회사 행의 연락처)는 행의 첫 줄이 아닐 수 있어 맨 뒤에 둔다."""
        own = list(self.evidence.get(path, []))
        parent = re.sub(r"\[\d+\]$", "", path)
        page = next((p for p, _ in own), None) or next((p for p, _ in self.evidence.get(parent, [])), None)
        probes = [(page, t) for t in row_values(value)]
        sub = [a for f, xs in self.evidence.items() if f.startswith(path + ".") or f.startswith(path + "[") for a in xs]
        return own + probes + sub

    def locate(self, path: str, value, table: str | None = None) -> str | None:
        """줄 번호, OUTSIDE(이 항 줄 밖에만 있음), NO_ANCHOR(찾을 글 없음), 또는 None(어디에도 없음).
        근거 조각이 제목 줄에서 시작하고 값은 다음 줄에 있으면(예: '● 생분해성' 다음 줄에 값) 값이 있는 줄을 쓴다.
        안내문 규칙이 '그 값이 적힌 줄'이기 때문이다."""
        after = self.cursor.get(table, -1) if table else -1
        anchors = self.anchors(path, value)
        values = [norm(v) for v in row_values(value) if len(norm(v)) >= 2]
        outside = False
        for page, text in anchors:
            i = self.finder.find(text, page, after)
            if i is not None:
                if values and not any(v in self.finder.norms[i] for v in values):
                    nxt = [j for j in range(i + 1, min(i + 4, len(self.finder.lines)))
                           if any(v in self.finder.norms[j] for v in values)]
                    i = nxt[0] if nxt else i
                if table:
                    self.cursor[table] = i
                return self.finder.lines[i].id
            outside = outside or self.doc_finder.find(text, page) is not None
        return OUTSIDE if outside else NO_ANCHOR if not anchors else None

    def row_line(self, path: str, value, table: str | None) -> str | None:
        """행의 줄. 행을 정답에서 빼야 하면 None과 함께 notes에 남긴다. 못 찾으면 problems."""
        got = self.locate(path, value, table)
        if got == OUTSIDE:
            self.notes.append(f"이 항 줄 밖 {path}")
            return None
        if got == NO_ANCHOR:
            self.notes.append(f"근거 글 없는 행 {path}")
            return None
        if got is None:
            self.problems.append(f"줄 못 찾음 {path}")
        return got

    def field_line(self, path: str, value) -> str | None:
        """객체 칸의 줄. 칸을 정답에서 빼야 하면 OUTSIDE."""
        got = self.locate(path, value)
        if got == OUTSIDE and path not in INFERRED:
            self.notes.append(f"이 항 줄 밖 {path}")
            return OUTSIDE
        if got in (OUTSIDE, NO_ANCHOR, None) and (path in INFERRED or isinstance(value, bool)):
            return self.first_line
        if got in (NO_ANCHOR, None):
            self.problems.append(f"줄 못 찾음 {path}")
            return None
        return got


def _conv(value, node: dict, defs: dict, path: str, ctx: _Ctx, table: str | None = None):
    if value is None:
        return None
    node, name = _resolve(node, defs)
    if name == "QM":
        q = {k: value.get(k) for k in QM_FIELDS if isinstance(value, dict) and value.get(k) is not None}
        return q or None
    t = node.get("type")
    if t == "array":
        items = node.get("items") or {}
        if not isinstance(value, list):
            return None
        rows = [_conv(v, items, defs, f"{path}[{i}]", ctx, path) for i, v in enumerate(value)]
        return [r for r in rows if r is not _DROP]
    if t == "object" and "properties" in node and isinstance(value, dict):
        props = node["properties"]
        out = {}
        for k, sub in props.items():
            if k in ("line", "lines"):
                continue
            if k in ("comp_name", "comp_cas"):
                c = ctx.components.get(str(value.get("comp_ref"))) if value.get("comp_ref") not in (None, "MIX") else None
                if value.get("comp_ref") not in (None, "MIX") and c is None:
                    ctx.problems.append(f"성분 번호 없음 {path}.comp_ref={value.get('comp_ref')}")
                v = (c or {}).get("name" if k == "comp_name" else "cas_no")
            else:
                v = _conv(value.get(k), sub, defs, f"{path}.{k}", ctx)
            if v is not None and v != [] and v != {}:
                out[k] = v
        if "line" in props:                                  # 행: 이 항이 볼 수 없는 행은 뺀다(_DROP)
            line = ctx.row_line(path, value, table)
            if line is None and not any(p.endswith(path) for p in ctx.problems):
                return _DROP
            out["line"] = line
        if "lines" in props:                                 # 객체 칸: 값이 있는 칸마다 줄
            keys = props["lines"].get("properties") or {}
            lines = {}
            for k in keys:
                if out.get(k) in (None, [], {}):
                    continue
                got = ctx.field_line(f"{path}.{k}", value.get(k))
                if got == OUTSIDE:
                    out.pop(k, None)
                else:
                    lines[k] = got
            out["lines"] = lines
        return out
    return value


_DROP = object()          # 정답에서 뺄 행


def _narratives(item: dict, codes: tuple[str, ...], ctx: _Ctx) -> list[dict]:
    """서술 항목: 시작 줄은 근거 조각·제목·첫 문장으로, 끝 줄은 뒤 문장부터 찾은 첫 문장으로 정한다.
    시작이 이 항 줄 밖에만 있으면 그 항목을 뺀다."""
    rows = []
    for i, r in enumerate(item.get("narratives") or []):
        if not isinstance(r, dict) or r.get("item_code") not in codes:
            continue
        path = f"narratives[{i}]"
        stmts = [s for s in r.get("statements") or [] if isinstance(s, dict)]
        heads = list(ctx.evidence.get(path, [])) + [(None, r.get("title_raw"))] + \
            [(None, s.get("text") or s.get("value")) for s in stmts[:1]]
        heads = [(p, t) for p, t in heads if t]
        start = next((k for p, t in heads for k in [ctx.finder.find(t, p, ctx.cursor.get("narratives", -1))]
                      if k is not None), None)
        if start is None:
            if any(ctx.doc_finder.find(t, p) is not None for p, t in heads):
                ctx.notes.append(f"이 항 줄 밖 {path}")
            elif heads:
                ctx.problems.append(f"줄 못 찾음 {path} 시작")
            else:
                ctx.notes.append(f"근거 글 없는 행 {path}")
            continue
        end = start
        for s_ in reversed(stmts):
            k = ctx.finder.find(s_.get("text") or s_.get("value"), None, start)
            if k is not None and k >= start:
                end = k
                break
        ctx.cursor["narratives"] = end
        row = {"item_code": r["item_code"]}
        if r.get("title_raw"):
            row["title_raw"] = r["title_raw"]
        row.update(start=ctx.finder.lines[start].id, end=ctx.finder.lines[end].id)
        rows.append(row)
    return rows


def convert_section(item: dict, no: int, doc, msds_index: int) -> tuple[dict, list[str], list[str]]:
    """TO21 msds 항목 하나 → no항 중간 형식 응답. 반환: (응답, problems, notes).
    problems가 비어 있지 않으면 줄을 못 찾은 행·칸이 있다. notes는 이 항이 볼 수 없어 뺀 행·칸이다."""
    schema = response_schema(no)
    defs = schema.get("$defs", {})
    first, last = doc.msds[msds_index].pages
    span = section_lines(doc, msds_index, no, with_preamble=False)
    ctx = _Ctx(item, LineFinder(section_lines(doc, msds_index, no)),
               LineFinder([l for l in doc.lines if first <= l.page <= last]), span[0].id if span else None)
    spec = load_specs()[no]
    out: dict = {}
    for key, node in schema["properties"].items():
        if key == "narratives":
            out[key] = _narratives(item, spec.narrative_codes, ctx)
        elif key == "extras":
            rows = [(i, r) for i, r in enumerate(item.get("extras") or []) if isinstance(r, dict) and r.get("section_no") == no]
            row_node = node["items"]
            out[key] = [x for x in (_conv(r, row_node, defs, f"extras[{i}]", ctx, "extras") for i, r in rows) if x is not _DROP]
        else:
            v = _conv(item.get(key), node, defs, key, ctx)
            out[key] = v if v is not None else ({"lines": {}} if node.get("type") == "object" else [])
    return out, ctx.problems, ctx.notes
