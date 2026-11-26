"""단계별 지표 계산 함수 (역할 C). 최종 칸 점수(score.py) 앞 단계가 얼마나 정확한지 잰다.

- 글자·낱말: edit_distance, cer, wer, substring_distance
- 표 구조: table_tree, read_md_table, teds (PubTabNet의 TEDS. Zhong et al., ECCV 2020)
- 정답 근거 글 대조: snippet_parts, snippet_score, dedupe_evidence
  골드의 evidence.source_text는 사람이 원문에서 옮겨 적은 글이다. 표 칸은 " | "로 이어 적었다
- 틀린 칸 원인 나누기: detail_values, value_found (채점기 오류 상세의 정답 값이 입력 글에 있는가)

외부 라이브러리 없이 numpy만 쓴다 (폐쇄망).
"""
from __future__ import annotations

import ast
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

_WS = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    """NFKC 뒤 공백·줄바꿈을 모두 지운다. 띄어쓰기는 OCR·텍스트층 모두 흔들려 보지 않는다."""
    return _WS.sub("", unicodedata.normalize("NFKC", text or ""))


# ── 편집 거리 ──────────────────────────────────────────
def _codes(a, b) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(a, str) and isinstance(b, str):
        return (np.frombuffer(a.encode("utf-32-le"), dtype=np.uint32),
                np.frombuffer(b.encode("utf-32-le"), dtype=np.uint32))
    vocab: dict = {}
    ids = lambda s: np.array([vocab.setdefault(x, len(vocab)) for x in s], dtype=np.int64)  # noqa: E731
    return ids(a), ids(b)


def _dp(pat: np.ndarray, text: np.ndarray, free_start: bool) -> np.ndarray:
    """pat을 한 글자씩 넣으며 text 쪽 행을 갱신한 마지막 행. free_start면 text 어디서든 시작할 수 있다.

    한 행 안의 삽입 항 D[j] = min(D[j], D[j-1]+1)은 D[j]-j의 누적 최솟값으로 한 번에 푼다.
    """
    n = len(text)
    j = np.arange(n + 1)
    prev = np.zeros(n + 1, dtype=np.int64) if free_start else j.astype(np.int64)
    for i, ch in enumerate(pat, 1):
        cur = np.empty(n + 1, dtype=np.int64)
        cur[0] = i
        cur[1:] = np.minimum(prev[:-1] + (text != ch), prev[1:] + 1)
        cur = np.minimum.accumulate(cur - j) + j
        prev = cur
    return prev


def edit_distance(a, b) -> int:
    """레벤시테인 거리. 문자열이면 글자, 리스트면 원소 단위."""
    if len(a) == 0 or len(b) == 0:
        return max(len(a), len(b))
    x, y = _codes(a, b)
    return int(_dp(x, y, free_start=False)[-1])


def substring_distance(pat: str, text: str) -> int:
    """pat과 text의 한 구간 사이 가장 작은 편집 거리 (구간 앞뒤는 공짜). 정답 조각이 쪽 어딘가에 있는가."""
    if not pat:
        return 0
    if not text:
        return len(pat)
    x, y = _codes(pat, text)
    return int(_dp(x, y, free_start=True).min())


def cer(ref: str, hyp: str) -> float | None:
    """글자 오류율 = 편집 거리 / 정답 글자 수 (공백 제외, NFKC). 정답이 비면 None."""
    r, h = normalize(ref), normalize(hyp)
    return edit_distance(r, h) / len(r) if r else None


def bag_cer(ref: str, hyp: str) -> float | None:
    """순서를 보지 않는 글자 오류율. 글자 묶음 차이(빠진 글자·남는 글자 중 많은 쪽) / 정답 글자 수.

    cer는 읽기 순서가 달라도 오류로 세서 크게 나오고, 이 값은 순서 오류를 지워 작게 나온다.
    둘의 차이가 크면 글자 인식보다 읽기 순서가 문제다.
    """
    r, h = Counter(normalize(ref)), Counter(normalize(hyp))
    n = sum(r.values())
    return max(sum((r - h).values()), sum((h - r).values())) / n if n else None


def wer(ref: str, hyp: str) -> float | None:
    """낱말 오류율. 공백으로 나눈 낱말 단위. 한국어는 띄어쓰기가 흔들려 CER보다 크게 나온다."""
    r = unicodedata.normalize("NFKC", ref or "").split()
    h = unicodedata.normalize("NFKC", hyp or "").split()
    return edit_distance(r, h) / len(r) if r else None


# ── 표 구조 (TEDS) ──────────────────────────────────────
@dataclass
class Node:
    tag: str
    text: str = ""
    rowspan: int = 1
    colspan: int = 1
    children: list["Node"] = field(default_factory=list)


def table_tree(rows: list[list[str]], spans: list[dict] | None = None) -> Node:
    """표 → table/tr/td 나무. spans(r행 c열에서 rs행 cs열)에 가려진 칸은 넣지 않는다."""
    hidden, span_at = set(), {}
    for s in spans or []:
        span_at[(s["r"], s["c"])] = (s["rs"], s["cs"])
        for dr in range(s["rs"]):
            for dc in range(s["cs"]):
                if dr or dc:
                    hidden.add((s["r"] + dr, s["c"] + dc))
    table = Node("table")
    for r, row in enumerate(rows):
        tr = Node("tr")
        for c, text in enumerate(row):
            if (r, c) in hidden:
                continue
            rs, cs = span_at.get((r, c), (1, 1))
            tr.children.append(Node("td", text=normalize(text), rowspan=rs, colspan=cs))
        table.children.append(tr)
    return table


def read_md_table(md: str) -> list[list[str]]:
    """전처리가 쓴 마크다운 표(tables/*.md) → 칸 목록. 둘째 줄(--- 구분선)은 뺀다."""
    lines = [ln.strip()[1:-1] for ln in md.splitlines() if ln.strip().startswith("|")]
    return [[c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", ln)]
            for i, ln in enumerate(lines) if i != 1]


def line_tables(text: str) -> list[list[list[str]]]:
    """모델 입력 글에서 표 줄을 묶는다. 칸 구분(' | ')이 있는 줄이 이어진 구간 하나가 표 하나다.

    전처리가 표 파일(tables/*.md)을 따로 만들지 않은 쪽도 모델은 이 줄을 표로 읽는다.
    칸 구분 없는 줄(제목, 다음 줄로 넘어간 값)이 끼면 표가 끊긴다. 그것도 모델이 받은 그대로다.
    """
    out, cur = [], []
    for line in (text or "").splitlines():
        if "|" in line:
            cur.append([c.strip() for c in line.split("|")])
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def row_kept(cells: list[str], page_norm: str, tol: float = 0.1) -> bool:
    """행 보존: 행의 칸 글자를 이은 것이 쪽 글(normalize한 것)의 한 구간에 있는가.

    줄바꿈·띄어쓰기·칸 구분('|')은 보지 않는다. 글자 tol 비율까지 틀려도 봐준다(OCR 몇 글자 오인식).
    """
    row = "".join(normalize(c) for c in cells)
    if not row:
        return False
    return substring_distance(row, page_norm.replace("|", "")) <= tol * len(row)


def boundary_kept(cells: list[str], page_norm: str, edge: int = 8) -> bool | None:
    """경계 전달: 이웃한 칸 사이에 칸 구분('|')이 들어가 모델에게 전달됐는가.

    빈 칸은 건너뛰고, 글이 든 칸이 둘 미만이면 None. 앞 칸 끝 edge자 + '|' + 뒤 칸 앞 edge자가
    쪽 글에 그대로 있어야 한다(빈 칸 자리의 '||'는 하나로 본다). 띄어쓰기는 칸 안에도 있어 경계로 치지 않는다.
    """
    parts = [normalize(c) for c in cells if normalize(c)]
    if len(parts) < 2:
        return None
    flat = re.sub(r"\|+", "|", page_norm)
    return all(f"{a[-edge:]}|{b[:edge]}" in flat for a, b in zip(parts, parts[1:]))


def _postorder(root: Node) -> tuple[list[Node], list[int]]:
    """후위 순회 노드와 각 노드의 가장 왼쪽 잎 번호."""
    nodes, lml = [], []

    def go(n: Node) -> int:
        first = None
        for ch in n.children:
            leaf = go(ch)
            first = leaf if first is None else first
        nodes.append(n)
        lml.append(first if first is not None else len(nodes) - 1)
        return lml[-1]

    go(root)
    return nodes, lml


def _rename(a: Node, b: Node, structure_only: bool) -> float:
    if a.tag != b.tag:
        return 1.0
    if a.tag != "td":
        return 0.0
    if (a.rowspan, a.colspan) != (b.rowspan, b.colspan):
        return 1.0
    if structure_only or a.text == b.text:
        return 0.0
    return edit_distance(a.text, b.text) / max(len(a.text), len(b.text))


def tree_edit_distance(a: Node, b: Node, structure_only: bool = False) -> float:
    """Zhang–Shasha 나무 편집 거리. 넣기·지우기 1, 바꾸기는 _rename."""
    an, al = _postorder(a)
    bn, bl = _postorder(b)
    keyroots = lambda lml: sorted({max(i for i in range(len(lml)) if lml[i] == l) for l in set(lml)})  # noqa: E731,E741
    td = np.zeros((len(an), len(bn)))
    for i in keyroots(al):
        for j in keyroots(bl):
            li, lj = al[i], bl[j]
            m, n = i - li + 2, j - lj + 2
            fd = np.zeros((m, n))
            fd[1:, 0] = np.arange(1, m)
            fd[0, 1:] = np.arange(1, n)
            for x in range(li, i + 1):
                for y in range(lj, j + 1):
                    xi, yi = x - li + 1, y - lj + 1
                    if al[x] == li and bl[y] == lj:
                        fd[xi, yi] = min(fd[xi - 1, yi] + 1, fd[xi, yi - 1] + 1,
                                         fd[xi - 1, yi - 1] + _rename(an[x], bn[y], structure_only))
                        td[x, y] = fd[xi, yi]
                    else:
                        fd[xi, yi] = min(fd[xi - 1, yi] + 1, fd[xi, yi - 1] + 1,
                                         fd[al[x] - li, bl[y] - lj] + td[x, y])
    return float(td[-1, -1])


def _size(n: Node) -> int:
    return 1 + sum(_size(c) for c in n.children)


def teds(gold: Node, pred: Node, structure_only: bool = False) -> float:
    """TEDS = 1 - 나무 편집 거리 / 큰 쪽 노드 수. structure_only면 칸 글자를 보지 않는다(TEDS-S)."""
    return 1.0 - tree_edit_distance(gold, pred, structure_only) / max(_size(gold), _size(pred))


# ── 정답 근거 글 대조 ────────────────────────────────────
_PICTURE_NOTE = re.compile(r"\([^()]*그림\)")      # "(가스 실린더 그림)": 그림문자를 사람이 말로 적은 것
_ELLIPSIS = re.compile(r"\.{3,}|…")                 # 사람이 줄여 적은 자리


def snippet_parts(source_text: str) -> list[str]:
    """evidence.source_text를 원문에서 찾을 조각으로 나눈다.

    표 칸(" | ")과 줄임표("...")에서 나누고, 그림문자 설명("(… 그림)")은 원문 글자가 아니라 지운다.
    조각 사이 순서는 읽기 순서에 따라 바뀔 수 있어 조각마다 따로 찾는다.
    """
    text = _PICTURE_NOTE.sub("|", source_text or "")
    text = _ELLIPSIS.sub("|", text)
    return [p.strip() for p in text.split("|") if len(normalize(p)) >= 2]


def snippet_score(source_text: str, page_text: str) -> dict:
    """정답 근거 글이 쪽 글에 얼마나 그대로 있는가. errors는 칸마다 쪽 안 가장 가까운 구간과의 편집 거리 합."""
    page = normalize(page_text)
    errors = chars = 0
    for part in snippet_parts(source_text):
        p = normalize(part)
        errors += substring_distance(p, page)
        chars += len(p)
    return {"errors": errors, "chars": chars, "exact": errors == 0}


def dedupe_evidence(evidence: list[dict]) -> list[tuple[int, str]]:
    """(쪽, 근거 글) 목록. 같은 글을 여러 칸이 근거로 쓴 것은 한 번만 센다."""
    seen: dict[tuple[int, str], None] = {}
    for e in evidence:
        if e.get("source_text") and e.get("page"):
            seen.setdefault((int(e["page"]), e["source_text"]), None)
    return list(seen)


# ── 틀린 칸 원인 나누기 ──────────────────────────────────
# 정답 값이 원문 글자가 아니라 판단·상태인 값 (채점기 상세에 섞여 나온다)
STATUS_WORDS = {"값있음", "자료없음", "해당없음", "미기재", "비해당", "해당", "미표기", "결과기술",
                "이미지판독", "수기", "필드없음"}
_CODE = re.compile(r"^[A-Z_]+$")          # MIX, BOILING, ACGIH 같은 사전 코드
_NUM = re.compile(r"\d+(?:\.\d+)?")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")   # 1,004 → 1004 (1,3-부타디엔은 그대로)
_CAS = re.compile(r"^\d{2,7}-\d{2}-\d$")


def _source_like(v) -> str | None:
    if v is None or isinstance(v, bool):
        return None
    s = repr(v) if isinstance(v, float) else str(v)
    if isinstance(v, str) and (_CODE.match(v) or v in STATUS_WORDS):
        return None
    return s if len(normalize(s)) >= 2 else None


def detail_values(content) -> list[str]:
    """채점기 오류 상세 한 건에서 정답 쪽 값 중 원문에 글자로 나올 만한 것."""
    if isinstance(content, str):
        m = re.match(r"정답=(.*?) / 추출=", content)
        if not m:
            return []
        try:
            content = ast.literal_eval(m.group(1))
        except (ValueError, SyntaxError):
            content = m.group(1)
    out: list[str] = []

    def walk(x):
        if isinstance(x, (list, tuple)):
            for y in x:
                walk(y)
        elif (s := _source_like(x)) is not None:
            out.append(s)

    walk(content)
    # 수가 있는 오류는 수·CAS 번호만 본다. 부등호·단위·분류 이름은 원문 표기가 달라(>= → 이상, g/cm3 → g/㎤)
    # 찾지 못해도 입력에 없다는 뜻이 아니다
    core = [v for v in out if _is_number(v) or _CAS.match(v)]
    return core or out


def _is_number(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def value_found(value: str, text: str) -> bool:
    """값이 글에 있는가. 숫자는 수로 비교(끝자리 0, 부호 띄어쓰기, 천 단위 쉼표 봐줌), 글은 공백·NFKC·대소문자 무시."""
    if not _is_number(value):
        return normalize(value).casefold() in normalize(text).casefold()
    v = abs(float(value))
    flat = _THOUSANDS.sub("", unicodedata.normalize("NFKC", text or ""))   # 공백은 남긴다: LD50 5480이 붙지 않게
    return any(abs(float(x)) == v for x in _NUM.findall(flat))


# ── 반복 실행 안정도 ─────────────────────────────────────
# 실행마다 달라도 내용이 아닌 칸: 근거 기록, 순번, 줄 번호, 추출 시각·모델 정보
_BOOKKEEPING = {"evidence", "seq", "line", "lines", "extraction"}


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if k not in _BOOKKEEPING}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def field_agreement(a: dict, b: dict) -> dict[str, dict]:
    """같은 입력·설정으로 두 번 뽑은 MSDS 하나(msds[i])가 칸별로 얼마나 같은가.

    목록 칸(toxicity, regulations 등)은 행 순서를 보지 않고 똑같은 행의 수를 센다(한쪽에만 있는 행은 다름).
    total은 두 실행 중 행이 많은 쪽. 객체 칸(product, hazard 등)은 아래 칸 하나하나를 한 행으로 센다.
    행 안의 칸 하나만 달라도 다른 행으로 세는 엄격한 기준이다.
    """
    out: dict[str, dict] = {}
    for key in sorted((set(a) | set(b)) - _BOOKKEEPING):
        va, vb = _clean(a.get(key)), _clean(b.get(key))
        if isinstance(va, list) or isinstance(vb, list):
            ca = Counter(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in va or [])
            cb = Counter(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in vb or [])
            out[key] = {"same": sum((ca & cb).values()), "total": max(sum(ca.values()), sum(cb.values()))}
        elif isinstance(va, dict) or isinstance(vb, dict):
            da, db = va or {}, vb or {}
            subs = set(da) | set(db)
            out[key] = {"same": sum(da.get(s) == db.get(s) for s in subs), "total": len(subs)}
        else:
            out[key] = {"same": int(va == vb), "total": 1}
    return out
