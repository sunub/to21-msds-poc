"""검수표 → 골드 JSON — 역할 A가 채운다 (D-33, D-36).

사람은 JSON을 고치지 않는다. 검수표만 고치고, 골드는 이 스크립트가 만든다.
같은 검수표로 다시 돌리면 같은 골드가 나와야 한다.

이미 있는 도구
- common.align.unflatten_keyed(pairs)  키 경로와 값 목록 → msds 항목
- common.jsonpath.from_cell(text)      사람이 적은 수정값 → 값 (JSON이면 JSON)
- common.schema.validate_to21(doc)     TO21 스키마 검증
- checks.validator.run_to21_validator  TO21 검증기

완료 확인: pytest tests/test_A_review.py
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
from pathlib import Path

import openpyxl

from msds.checks.validator import run_to21_validator
from msds.common import paths
from msds.common.align import generic, keyed_flatten, unflatten_keyed
from msds.common.jsonpath import from_cell
from msds.common.schema import load_schema, msds_item_schema, validate_to21

from .make_sheet import in_scope
from .sheet_spec import COLUMNS, DEFAULT_MODEL, EXCLUDED_TOP, RESULT_OPTIONS, SHEET_INFO, SHEET_MAIN

TAGS = {"gpt": "GPT", "claude": "Claude"}
ADOPT = {"GPT 채택": "GPT", "Claude 채택": "Claude"}
_ROW_PATH = re.compile(r"msds\[(\d+)\]\.(.+)")
_SEG = r"[^.\[\]]+(?:\[(?:k=[^\]]*|\d+)\])*"
_KEY_PATH = re.compile(rf"{_SEG}(?:\.{_SEG})*")
_LIST_TOK = re.compile(r"\[(?:k=[^\]]*|\d+)\]")
# 키 경로 항목 → 번호 경로 (가이드 3.5). unflatten_keyed가 항목을 놓는 순서(처음 나온 순서)와 같게 센다
_TOK = re.compile(r"\.?([^.\[\]]+)|\[k=([^\]]*)\]|\[(\d+)\]")
# 근거로 쓸 줄의 우선: 검수자가 적은 줄 > 채택한 줄 > 미검수 줄
RANK_REVIEWER, RANK_ADOPT, RANK_DEFAULT = 0, 1, 2


def _excel_value(v):
    """엑셀이 날짜로 바꾼 값(따옴표 없이 적은 날짜)은 글자로 되돌린다."""
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time() else v.isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    return v


def read_sheet(path: Path) -> tuple[list[dict], dict]:
    """검수표를 읽어 (행 목록, 문서 정보)를 돌려준다. 빈 칸은 ''."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    it = wb[SHEET_MAIN].iter_rows(values_only=True)
    head = ["" if h is None else str(h) for h in next(it)]
    missing = [c for c in COLUMNS if c not in head]
    if missing:
        raise ValueError(f"{path}: 검수표 열이 없음 {missing}")
    rows = []
    for r in it:
        row = dict.fromkeys(COLUMNS, "")
        row.update({h: _excel_value(v) for h, v in zip(head, r) if h and v is not None})
        if any(v != "" for v in row.values()):
            rows.append(row)
    info = {str(r[0]): ("" if len(r) < 2 or r[1] is None else _excel_value(r[1]))
            for r in wb[SHEET_INFO].iter_rows(values_only=True) if r and r[0] is not None}
    wb.close()
    return rows, info


def _items(p: str) -> list[str]:
    """경로 안의 목록 항목 경로들(바깥 → 안쪽)."""
    return [p[:m.end()] for m in _LIST_TOK.finditer(p)]


def _under(p: str, prefixes) -> bool:
    return any(p == x or p.startswith(x + ".") or p.startswith(x + "[") for x in prefixes)


def _order_key(p: str) -> str:
    """경로 순서: 같은 키의 항목은 원래 순서(PH, PH#2, PH#3, … PH#10)대로."""
    return re.sub(r"#(\d+)\]", lambda m: f"#{int(m.group(1)):05d}]", p).replace("]", "\x00")


def _parent_list(x: str) -> str:
    return x[:x.rfind("[")]


def index_map(pairs: list[tuple[str, object]]) -> dict[str, str]:
    """키 경로(칸과 그 앞부분 모두) → 번호 경로."""
    seen: dict = {}
    out: dict[str, str] = {}
    for p, _ in pairs:
        ip = kp = ""
        for m in _TOK.finditer(p):
            name, key, idx = m.groups()
            if name is not None:
                ip += ("." if ip else "") + name
                kp += ("." if kp else "") + name
            else:
                is_key = m.group(0).startswith("[k=")
                d = seen.setdefault(ip, {})
                n = d.setdefault((is_key, key if is_key else idx), len(d))
                ip += f"[{n}]"
                kp += f"[k={key}]" if is_key else f"[{idx}]"
            out.setdefault(kp, ip)
    return out


def _resolve(s: dict) -> dict:
    while "$ref" in s:
        s = load_schema()["$defs"][s["$ref"].rsplit("/", 1)[1]]
    return s


def _branch(s: dict, typ: str) -> dict | None:
    s = _resolve(s)
    for a in [_resolve(x) for x in s.get("anyOf", [s])]:
        if a.get("type") == typ:
            return a
    return None


def _schema_at(gpath: str) -> dict | None:
    """번호·키를 지운 경로(components[])의 스키마. 빈 경로는 msds 항목."""
    s = msds_item_schema()
    for name, arr in re.findall(r"([^.\[\]]+)|(\[\])", gpath):
        s = (_branch(s, "array") or {}).get("items") if arr else ((_branch(s, "object") or {}).get("properties") or {}).get(name)
        if s is None:
            return None
    return _resolve(s)


def _blank(s: dict):
    """스키마에 맞는 빈 값: null 허용이면 None, 아니면 빈 목록·빈 객체."""
    s = _resolve(s)
    alts = [_resolve(a) for a in s.get("anyOf", [s])]
    if any(a.get("type") == "null" for a in alts):
        return None
    return {"array": [], "object": {}}.get(alts[0].get("type"))


def _empty(p: str, v):
    """비운 칸(None)이 null을 받지 않는 칸(글자 목록 등)이면 그 칸의 빈 값([])으로."""
    if v is None and (s := _schema_at(generic(p))) is not None:
        return _blank(s)
    return v


def _complete(node, s: dict):
    """새 MSDS 건: 스키마 순서대로 빠진 칸을 빈 값으로 채운다(안쪽 객체·목록 항목까지)."""
    obj, arr = _branch(s, "object"), _branch(s, "array")
    if isinstance(node, dict) and obj and "properties" in obj:
        props = obj["properties"]
        out = {k: _complete(node[k] if k in node else _blank(v), v) for k, v in props.items()}
        return out | {k: v for k, v in node.items() if k not in props}
    if isinstance(node, list) and arr:
        return [_complete(x, arr.get("items") or {}) for x in node]
    return node


def _fill(x: str, pairs: list) -> list:
    """새로 생긴 목록 항목 x의 빠진 칸을 빈 값으로, 비어 있는 seq를 마지막 번호 다음으로 채운다."""
    if any(p == x for p, _ in pairs):      # 서술 문장(STMT)처럼 항목 자체가 한 칸이면 그대로 둔다
        return []
    props = ((_schema_at(generic(x)) or {}).get("properties") or {})
    have = {re.split(r"[.\[]", p[len(x) + 1:], maxsplit=1)[0] for p, _ in pairs if p.startswith(x + ".")}
    add = [(f"{x}.{k}", _blank(v)) for k, v in props.items() if k not in have]
    if "seq" in props and dict(pairs).get(f"{x}.seq") is None:
        parent = _parent_list(x)
        sib = [v for p, v in pairs if isinstance(v, int) and re.fullmatch(re.escape(parent) + r"\[[^\]]*\]\.seq", p)]
        seq = max(sib, default=0) + 1
        pairs[:] = [(p, seq if p == f"{x}.seq" else v) for p, v in pairs]
        add = [(p, seq if p == f"{x}.seq" else v) for p, v in add]
    return add


def _decide(r: dict, dtag: str) -> tuple:
    """행 하나의 결정: (종류, 값, 원문 조각, 쪽, 근거 우선).
    종류 = set / del / skip(미검수인데 기본값 모델에 칸이 없음)."""
    res = str(r["검수 결과"]).strip()
    if res in ADOPT:
        t = ADOPT[res]
        other = next(x for x in TAGS.values() if x != t)
        if r["일치"] == f"{other}만":                # 칸이 없는 쪽을 채택 = 그 칸(항목)이 없어야 한다
            return "del", None, "", "", RANK_ADOPT
        return "set", from_cell(r[f"{t} 값"]), r[f"{t} 원문 조각"], r[f"{t} 쪽"], RANK_ADOPT
    if res in ("수정", "누락 추가"):
        return "set", from_cell(r["수정값"]), r["수정 원문 조각"], r["수정 쪽"], RANK_REVIEWER
    if res == "삭제":
        return "del", None, "", "", RANK_REVIEWER
    if res == "":
        other = next(t for t in TAGS.values() if t != dtag)
        if r["일치"] == f"{other}만":
            return "skip", None, "", "", RANK_DEFAULT
        return "set", from_cell(r[f"{dtag} 값"]), r[f"{dtag} 원문 조각"], r[f"{dtag} 쪽"], RANK_DEFAULT
    raise ValueError(f"검수 결과 '{res}'는 {RESULT_OPTIONS} 중 하나여야 함: {r['경로']}")


def _read_rows(rows: list[dict], dtag: str) -> dict[int, dict[str, tuple]]:
    dec: dict[int, dict[str, tuple]] = {}
    for r in rows:
        path = str(r["경로"]).strip()
        m = _ROW_PATH.fullmatch(path)
        if not m or not _KEY_PATH.fullmatch(m.group(2)):
            raise ValueError(f"경로 형식이 맞지 않음 (msds[i].이름[k=키].이름 …): {path}")
        i, kp = int(m.group(1)), m.group(2)
        k = (*_decide(r, dtag), bool(str(r["일치"]).strip()))     # 마지막: 스크립트가 만든 줄인가(사람이 넣은 줄이 아님)
        if kp in dec.get(i, {}) and dec[i][kp][:2] != k[:2]:
            raise ValueError(f"같은 경로의 줄이 둘 이상이고 결정이 다름: {path}")
        dec.setdefault(i, {})[kp] = k
    return dec


def _assemble(base: list, d: dict[str, tuple]) -> list[tuple[str, object]]:
    """기본값 실버의 펼친 순서에서 시작해 결정을 반영한 (키 경로, 값) 목록 (가이드 3.5)."""
    # 목록 항목 안의 줄을 삭제하면 그 항목 전체. 항목 자체가 한 칸(STMT)인 줄을 비워도 그 항목을 뺀다
    dead = {_items(p)[-1] for p, k in d.items() if _items(p) and
            (k[0] == "del" or (k[0] == "set" and k[1] is None and _items(p)[-1] == p))}
    pairs, seen, holes = [], set(), {}
    for p, v in base:
        if _under(p, dead):
            x = min((x for x in dead if _under(p, [x])), key=len)
            holes.setdefault(_parent_list(x), len(pairs))
            continue
        k = d.get(p)
        if k and k[0] in ("set", "del"):
            v = _empty(p, k[1])
        pairs.append((p, v))
        seen.add(p)
    for x in sorted({_items(p)[-1] for p, k in d.items() if _items(p) and k[0] == "del"}):
        rows_in = [k for p, k in d.items() if _under(p, [x])]
        if not any(k[5] for k in rows_in) and not any(_under(p, [x]) for p, _ in base):
            print(f"[경고] '삭제'한 항목이 검수표·실버 어디에도 없음(경로 확인): {x}")
        elif any(k[0] == "set" and k[4] != RANK_DEFAULT for k in rows_in):
            print(f"[경고] 같은 항목에 '삭제'와 채택·수정이 함께 있음 → 삭제함: {x}")

    # 기본값 실버에 없던 칸(다른 모델에만 있던 칸, 누락 추가). 검수표 정렬과 무관하게 경로 순서로 더한다
    # ponytail: 기본값 실버에 없는 MSDS 건을 통째로 채택하면 목록 항목이 키 순서가 됨(값은 같음). 두 모델을 쓸 때 다른 모델 실버 순서를 받으면 해결
    leaves = dict(pairs)
    for p, k in sorted(d.items(), key=lambda t: _order_key(t[0])):
        if p in seen or k[0] != "set" or _under(p, dead):
            continue
        for cut in (m.start() for m in re.finditer(r"[.\[]", p)):
            if leaves.get(p[:cut]) not in (None, [], {}):
                raise ValueError(f"경로 {p}: 앞부분 {p[:cut]}이 이미 한 칸(값)이라 그 안에 넣을 수 없음")
        if any(q.startswith(p + ".") or q.startswith(p + "[") for q in leaves):
            raise ValueError(f"경로 {p}: 여러 칸을 담은 자리라 한 값으로 바꿀 수 없음 (안쪽 칸의 줄을 고칠 것)")
        pairs.append((p, _empty(p, k[1])))
    # 항목을 모두 지운 목록은 키를 남기고 빈 목록으로
    for L, at in sorted(holes.items(), key=lambda t: -t[1]):
        if not _under(L, dead) and not any(p == L or p.startswith(L + "[") for p, _ in pairs):
            pairs.insert(at, (L, []))

    old = {x for p, _ in base for x in _items(p)}
    for x in dict.fromkeys(x for p, _ in pairs for x in _items(p) if x not in old):
        pairs += _fill(x, pairs)
    return pairs


def _evidence(pairs: list, d: dict[str, tuple]) -> list[dict]:
    """근거: 칸(목록이면 항목) 하나에 하나. 검수자가 적은 줄 > 채택한 줄 > 미검수 줄, 같으면 원문 조각이 있는 줄 (D-36)."""
    imap, best = index_map(pairs), {}
    for n, (p, _) in enumerate(pairs):
        k = d.get(p)
        if not k or k[0] != "set":
            continue
        text, page = str(k[2] or "").strip(), re.search(r"\d+", str(k[3] or ""))
        field = imap.get((_items(p) or [p])[-1])
        if field and (text or page):
            best.setdefault(field, []).append(((k[4], 0 if text else 1, n), text, int(page.group(0)) if page else None))
    out = []
    for field, cands in best.items():
        cands.sort(key=lambda c: c[0])
        (rank, _, _), text, page = cands[0]
        if page is None:      # 원문 조각 줄에 쪽이 없으면 같은 우선의 다른 줄 쪽
            page = next((c[2] for c in cands if c[0][0] == rank and c[2] is not None), None)
        out.append({"field": field, "page": page, "bbox": None, "source_text": text or None,
                    "confidence": None, "method": "수기", "needs_review": False})
    return out


def build_gold(rows: list[dict], base_doc: dict, default_model: str = DEFAULT_MODEL) -> tuple[dict, list[str]]:
    """행 목록으로 골드 문서를 만든다. 돌려주는 값: (골드 문서, 미검수 칸 경로 목록).

    base_doc은 기본값 모델(default_model)의 실버. 그 펼친 순서에서 시작해 행의 결정으로 값을 바꾸고(삭제는 빼고),
    실버에 없던 칸(다른 모델에만 있던 칸, 누락 추가)은 뒤에 더한 다음 조립한다 (가이드 3.5).
    """
    dec = _read_rows(rows, TAGS[default_model])
    base_items = base_doc.get("msds") or []
    msds, unreviewed = [], []
    for i in range(max([len(base_items) - 1, *dec]) + 1):
        # 검수 범위 밖 항(make_sheet.REVIEW_SECTIONS)은 검수하지 않으므로 실버 값을 옮기지 않고 비운다 (2026-10-29 기업 합의)
        base = [(p, v) for p, v in keyed_flatten(base_items[i])
                if re.split(r"[.\[]", p, maxsplit=1)[0] not in EXCLUDED_TOP and in_scope(p)] if i < len(base_items) else []
        d = {p: k for p, k in dec.get(i, {}).items() if in_scope(p)}
        pairs = _assemble(base, d)
        if not pairs:            # 기본값 실버에 없고 채택한 칸도 없는 MSDS 건은 만들지 않는다
            continue
        kept = dict(pairs)        # 미검수 칸: 골드에 실제로 들어간 칸만 (삭제된 항목 안의 칸은 뺀다)
        unreviewed += [f"msds[{len(msds)}].{p}" for p, k in sorted(d.items(), key=lambda t: _order_key(t[0]))
                       if k[4] == RANK_DEFAULT and k[0] == "set" and p in kept]
        item = _complete(unflatten_keyed(pairs), msds_item_schema())   # 비운 항·새 MSDS 건의 빠진 칸을 빈 값으로
        item["evidence"] = _evidence(pairs, d)
        item["validation"] = []
        msds.append(item)

    gold = copy.deepcopy(base_doc)
    gold["msds"] = msds
    gold["doc"]["msds_count"] = len(msds)
    gold["doc"]["extraction"] = {**(gold["doc"].get("extraction") or {}), "engine": "manual(gold)"}
    return gold, unreviewed


def default_model(doc_id: str) -> str:
    """골드의 기본값 모델: DEFAULT_MODEL, 그 실버가 없으면 다른 모델(팀 합의로 Claude 실버만 있는 경우). 검수 화면도 같은 판단에 쓴다."""
    model = DEFAULT_MODEL
    if not paths.silver_path(model, doc_id).exists():   # 팀 합의로 Claude 실버만 있는 경우
        model = next(m for m in TAGS if m != model)
    return model


def build_gold_file(doc_id: str) -> Path:
    """data/review/<문서>.xlsx → data/gold/<문서>.json (+ <문서>.unreviewed.json)."""
    rows, _ = read_sheet(paths.review_sheet_path(doc_id))
    model = default_model(doc_id)
    if model != DEFAULT_MODEL:
        print(f"[경고] 기본값 모델({DEFAULT_MODEL}) 실버가 없어 {model} 실버를 기본값으로 씀")
    base = json.loads(paths.silver_path(model, doc_id).read_text(encoding="utf-8"))
    gold, unreviewed = build_gold(rows, base, model)

    out = paths.gold_path(doc_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8")
    paths.gold_unreviewed_path(doc_id).write_text(json.dumps(unreviewed, ensure_ascii=False, indent=2), encoding="utf-8")

    schema_errs = validate_to21(gold)
    val_errs = [v for v in run_to21_validator(gold) if v["level"] == "오류"]
    print(f"{doc_id}: 스키마 오류 {len(schema_errs)}건, 검증기 오류 {len(val_errs)}건, 미검수 {len(unreviewed)}칸")
    for e in schema_errs:
        print(f"  스키마 {e}")
    for v in val_errs:
        print(f"  검증기 {v['rule']} {v['field']} {v['message']}")
    return out
