"""작업 화면 탭 ② 두 실행 비교 (역할 B, 개발 전용, ADR-025).

두 실행의 요약(b_app_runs.summarize_run)을 받아 조건·점수 차·바뀐 값·표 행 수와, 점수가 내려간 항목의 원인 후보를 낸다.
- 원인 문장은 실행 기록의 수치(조건, 호출 격자, 빠뜨림·지어냄·틀림 수, 문서별 점수, 행 수)에서만 만든다.
- 안내문 글 차이는 실행의 git 커밋을 임시 worktree(저장소 밖 tempfile 아래)로 꺼내 build_system을 불러 얻는다.
  글은 메모리에만 두고 파일에 쓰지 않는다 (D-47). worktree는 끝나면(실패해도) 지운다.
"""
import difflib
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import _common  # noqa: F401  src 경로 등록
from msds.evaluate.score import KINDS

DROP = -2.0          # 이만큼 넘게 내려간 항목(점)만 원인을 찾는다
TIMEOUT = 120        # worktree 만들기·안내문 만들기 각각의 시간 제한(초)
_MAX_CALLS = 5       # 호출 원인 문장 최대 수. 넘으면 나머지 수만 적는다

# 채점 항목 이름 앞부분 → 그 값을 만드는 항 번호. section_specs._SECTIONS(항 → TO21 키)와 score.TOP_TO_ITEMS(TO21 키 → 항목)로 맞춘다.
# 관리정보는 16항(meta_revision)이 1항 값을 채우고, 서술형(narratives)은 서술 항목 코드가 있는 항이 모두 만든다.
ITEM_SECTIONS: dict[str, list[int]] = {
    "MSDS 건수": [1], "관리정보": [1, 16], "제품명": [1],
    "신호어": [2], "그림문자": [2], "H 코드": [2], "P 코드": [2], "유해성 분류": [2],
    "구성성분": [3], "함유량": [3], "8항": [8], "9항": [9], "11항": [11], "12항": [12], "14항": [14], "15항": [15],
    "서술형": [2, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16],
}
# 채점 항목 이름 앞부분 → 그 항목이 세는 표 (compare_models.ROW_KEYS). 15항 해외 규제도 regulations 표다(TO21 채점기)
ITEM_TABLES: dict[str, list[str]] = {
    "구성성분": ["components"], "함유량": ["components"], "8항": ["exposure_limits"], "9항": ["physchem"],
    "11항 급성": ["toxicity"], "11항 기타": ["toxicity"], "11항 CMR": ["cmr"], "12항": ["ecotox"],
    "15항": ["regulations"],
}
TABLE_LABEL = {"components": "성분", "exposure_limits": "노출기준", "physchem": "물성", "toxicity": "독성",
               "cmr": "CMR", "ecotox": "생태 독성", "regulations": "규제"}
_RUN_KEYS = ("name", "model_tag", "prompt_version", "pages_dir", "concurrency", "git_commit")
_COMMIT = re.compile(r"[0-9a-f]{4,40}")
_PROMPTS: dict[tuple, str] = {}      # (커밋, 항, 행 형식) → 안내문 글. 메모리에만 둔다
_BUILD = ("import sys\n"
          "from msds.extract.section_prompts import build_system\n"
          "no, rows = int(sys.argv[1]), sys.argv[2] == '1'\n"
          "sys.stdout.write(build_system(no, True) if rows else build_system(no))\n")   # 행 형식 전 커밋은 rows 인자가 없다


def _lookup(table: dict, name: str):
    key = max((k for k in table if name.startswith(k)), key=len, default=None)
    return table[key] if key else []


def sections_of(item_name: str) -> list[int]:
    """채점 항목(이름 또는 앞부분) → 그 값을 만드는 항 번호."""
    return list(_lookup(ITEM_SECTIONS, item_name))


def _short(doc_id: str) -> str:
    return doc_id.removeprefix("T21-")


def _last(path) -> str:
    return str(path).rstrip("/").split("/")[-1] if path else "—"


def _pts(v) -> float | None:
    return None if v is None else v * 100


def _sub(b, a):
    return None if a is None or b is None else b - a


def _secs(nos) -> str:
    return "·".join(str(n) for n in nos) + "항"


# ── 조건 ───────────────────────────────────────────────

def _conditions(a: dict, b: dict) -> list[dict]:
    pairs = [("모델", "model_tag"), ("안내문 버전", "prompt_version"), ("입력 판", "pages_dir"),
             ("동시 호출", "concurrency"), ("코드 커밋", "git_commit")]
    out = []
    for what, key in pairs:
        va = a.get(key) or (a.get("model") if key == "model_tag" else None)
        vb = b.get(key) or (b.get("model") if key == "model_tag" else None)
        out.append({"what": what, "a": va, "b": vb, "changed": va != vb})
    return out


def _hashes(run: dict) -> dict[int, str]:
    return {int(k): v for k, v in (run.get("prompt_hashes") or {}).items()}


def _prompt_changed(a: dict, b: dict) -> list[int]:
    ha, hb = _hashes(a), _hashes(b)
    return sorted(n for n in set(ha) & set(hb) if ha[n] != hb[n])


def _same_conditions(a: dict, b: dict) -> bool:
    return not any(c["changed"] for c in _conditions(a, b)) and not _prompt_changed(a, b)


def _common_docs(a: dict, b: dict) -> list[str]:
    return sorted(set(a.get("docs") or []) & set(b.get("docs") or []))


# ── 원인 후보 ──────────────────────────────────────────

def _reason_conditions(nos: list[int], a: dict, b: dict) -> list[str]:
    out = []
    changed = [n for n in _prompt_changed(a, b) if n in nos]
    if changed:
        va, vb = a.get("prompt_version"), b.get("prompt_version")
        ver = f"{va} → {vb}" if va != vb else f"버전 {va} 그대로"
        out.append(f"안내문이 바뀌었다({ver}, {_secs(changed)})")
    cond = {c["what"]: c for c in _conditions(a, b)}
    if cond["모델"]["changed"]:
        out.append(f"모델이 바뀌었다({cond['모델']['a']} → {cond['모델']['b']})")
    if cond["입력 판"]["changed"]:
        out.append(f"입력 판이 바뀌었다({_last(cond['입력 판']['a'])} → {_last(cond['입력 판']['b'])})")
    if cond["동시 호출"]["changed"]:
        out.append(f"동시 호출 수가 바뀌었다({cond['동시 호출']['a']} → {cond['동시 호출']['b']})")
    return out


def _cell_where(doc_id: str, key: str) -> tuple[int, str]:
    m = re.fullmatch(r"m(\d+):(\d+)", key)
    no = int(m[2]) if m else int(key)
    return no, f"{_short(doc_id)}{f' {int(m[1]) + 1}번째 MSDS' if m else ''} {no}항"


def _reason_calls(nos: list[int], a: dict, b: dict) -> list[str]:
    """b에서만 실패·한도 걸림·재추출이 있는 호출. 실패 → 한도 → 재추출 순."""
    fail, limit, again = [], [], []
    ga, gb = a.get("grid") or {}, b.get("grid") or {}
    for d in _common_docs(a, b):
        for key, cb in sorted((gb.get(d) or {}).items()):
            no, where = _cell_where(d, key)
            if no not in nos:
                continue
            ca = (ga.get(d) or {}).get(key) or {}
            if cb.get("ok") is False and ca.get("ok") is not False:
                fail.append(f"B에서 {where} 호출이 실패했다")
            if cb.get("limit_kind") and not ca.get("limit_kind"):
                limit.append(f"B에서 {where}이 출력 한도({cb['limit_kind']})에 걸렸다")
            if cb.get("reextracted") and not ca.get("reextracted"):
                again.append(f"B에서 {where}이 검사에 걸려 다시 뽑았다(재추출)")
    out = fail + limit + again
    if len(out) > _MAX_CALLS:
        out = out[:_MAX_CALLS] + [f"그 밖에 B에서만 실패·한도 걸림·재추출이 {len(out) - _MAX_CALLS}건 더 있다"]
    return out


def _reason_kinds(name: str, a: dict, b: dict) -> list[str]:
    ia = next((i for i in a.get("items") or [] if i["name"] == name), {})
    ib = next((i for i in b.get("items") or [] if i["name"] == name), {})
    return [f"{k}이 {ia.get(k, 0)} → {ib.get(k, 0)}개로 늘었다" for k in KINDS if ib.get(k, 0) > ia.get(k, 0)]


def _reason_docs(name: str, a: dict, b: dict) -> list[str]:
    pa, pb = a.get("per_doc") or {}, b.get("per_doc") or {}
    drops = []
    for d in _common_docs(a, b):
        sa, sb = (pa.get(d) or {}).get("items", {}).get(name), (pb.get(d) or {}).get("items", {}).get(name)
        if sa is not None and sb is not None and sb < sa:
            drops.append(((sb - sa) * 100, d))
    if not drops:
        return []
    return ["문서별로는 " + ", ".join(f"{_short(d)} −{-v:.1f}" for v, d in sorted(drops)[:3]) + "점 내려갔다"]


def _reason_rows(name: str, a: dict, b: dict) -> list[str]:
    """결과 행 수가 정답에서 (정답의 5%와 1행 중 큰 것) 이상 더 멀어진 표."""
    out = []
    for t in _lookup(ITEM_TABLES, name):
        ra, rb = (a.get("rows") or {}).get(t), (b.get("rows") or {}).get(t)
        if not ra or not rb:
            continue
        gold = rb["gold"]
        if abs(rb["pred"] - gold) - abs(ra["pred"] - gold) >= max(1, gold * 0.05):
            out.append(f"{TABLE_LABEL[t]} 행이 {ra['pred']} → {rb['pred']} (정답 {gold})")
    return out


def explain_drop(item: dict, a: dict, b: dict) -> list[str]:
    """점수가 내려간 항목 하나의 원인 후보 문장. 근거(수치)가 있는 것만, 영향이 큰 것부터:
    조건 → 호출 → 빠뜨림·지어냄·틀림 → 문서 → 행 수 → (조건이 모두 같으면) 흔들림."""
    name, nos = item["name"], item.get("sections") or sections_of(item["name"])
    out = (_reason_conditions(nos, a, b) + _reason_calls(nos, a, b) + _reason_kinds(name, a, b)
           + _reason_docs(name, a, b) + _reason_rows(name, a, b))
    if _same_conditions(a, b):
        conc = b.get("concurrency")
        out.append(f"조건이 같으므로 모델 흔들림일 수 있다(동시 {f'{conc}개 ' if conc else ''}호출, ADR-014)")
    return out


# ── 비교 ───────────────────────────────────────────────

def _items(a: dict, b: dict) -> list[dict]:
    ia = {i["name"]: i for i in a.get("items") or []}
    ib = {i["name"]: i for i in b.get("items") or []}
    out = []
    for n in list(ib) + [n for n in ia if n not in ib]:
        x, y = ia.get(n) or {}, ib.get(n) or {}
        sa, sb = _pts(x.get("score")), _pts(y.get("score"))
        out.append({"name": n, "level": y.get("level") or x.get("level"), "a": sa, "b": sb, "delta": _sub(sb, sa),
                    "pass_a": x.get("pass"), "pass_b": y.get("pass"), "sections": sections_of(n)})
    return out


def _details(run: dict, docs: set) -> dict[str, list[tuple]]:
    out: dict[str, list[tuple]] = {}
    for x in run.get("details") or []:
        k = (x["doc_id"], x["kind"], x["content"])
        if x["doc_id"] in docs and k not in out.setdefault(x["item"], []):
            out[x["item"]].append(k)
    return out


def _changed_values(a: dict, b: dict) -> dict:
    """두 실행 모두 채점한 문서의 틀린 값(details)을 (문서, 종류, 내용)으로 견준다.
    fixed = A에서 틀렸는데 B에서 사라진 것, broken = B에서 새로 틀린 것."""
    docs = set(_common_docs(a, b))
    ka, kb = _details(a, docs), _details(b, docs)
    res = {}
    for name in list(ka) + [n for n in kb if n not in ka]:
        la, lb = ka.get(name, []), kb.get(name, [])
        fixed = [dict(zip(("doc_id", "kind", "content"), k)) for k in la if k not in lb]
        broken = [dict(zip(("doc_id", "kind", "content"), k)) for k in lb if k not in la]
        if fixed or broken:
            res[name] = {"fixed": fixed, "broken": broken}
    return res


def _rows(a: dict, b: dict) -> dict:
    ra, rb = a.get("rows") or {}, b.get("rows") or {}
    return {t: {"a": (ra.get(t) or {}).get("pred"), "b": (rb.get(t) or {}).get("pred"),
                "gold": (rb.get(t) or ra.get(t) or {}).get("gold")}
            for t in list(rb) + [t for t in ra if t not in rb]}


def diff_runs(a: dict, b: dict) -> dict:
    """a, b는 summarize_run 결과. 점수는 0~100, delta = b − a.
    docs는 두 실행의 채점 문서 비교다. 문서가 다르면 항목 점수도 다른 문서 묶음의 평균이라 화면에 알린다.
    same_conditions는 조건·안내문 해시가 모두 같고 채점 문서도 같을 때만 참이다(그때 차이는 흔들림일 수 있다)."""
    items = _items(a, b)
    da, db = set(a.get("docs") or []), set(b.get("docs") or [])
    drops = sorted((i for i in items if i["delta"] is not None and i["delta"] <= DROP), key=lambda i: i["delta"])
    return {
        "a": {k: a.get(k) for k in _RUN_KEYS}, "b": {k: b.get(k) for k in _RUN_KEYS},
        "conditions": _conditions(a, b),
        "prompt_changed_sections": _prompt_changed(a, b),
        "same_conditions": _same_conditions(a, b) and da == db,
        "docs": {"common": sorted(da & db), "only_a": sorted(da - db), "only_b": sorted(db - da)},
        "items": items,
        "weighted": {"a": a.get("weighted"), "b": b.get("weighted"),
                     "delta": _sub(b.get("weighted"), a.get("weighted"))},
        "weighted_na_excluded": {"a": a.get("weighted_na_excluded"), "b": b.get("weighted_na_excluded"),
                                 "delta": _sub(b.get("weighted_na_excluded"), a.get("weighted_na_excluded"))},
        "changed_values": _changed_values(a, b),
        "rows": _rows(a, b),
        "causes": [{"item": i["name"], "delta": i["delta"], "reasons": explain_drop(i, a, b)} for i in drops],
    }


# ── 안내문 글 차이 ─────────────────────────────────────

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]      # section_prompts.prompt_hash와 같은 규칙


def _system_cached(commit: str, no: int, rows: bool, repo_root: Path) -> str:
    key = (commit, no, rows)
    if key not in _PROMPTS:
        _PROMPTS[key] = _system_at_commit(commit, no, rows, repo_root)
    return _PROMPTS[key]


def prompt_diff(no: int, rows: bool, commit_a: str, commit_b: str, repo_root: Path, *, builder=None,
                rows_b: bool | None = None) -> dict:
    """A 커밋과 B 커밋의 no항 안내문 글 차이. rows_b는 B 실행의 행 형식 여부가 A와 다를 때만 준다.
    builder(commit) -> 글 이 있으면 그것을 쓴다(시험용). 결과는 파일에 쓰지 않는다."""
    rows_b = rows if rows_b is None else rows_b
    if builder:
        ta, tb = builder(commit_a), builder(commit_b)
    else:
        ta, tb = _system_cached(commit_a, no, rows, repo_root), _system_cached(commit_b, no, rows_b, repo_root)
    la, lb = ta.splitlines(), tb.splitlines()
    diff = difflib.unified_diff(la, lb, f"A {commit_a} {no}항", f"B {commit_b} {no}항", lineterm="")
    return {"section": no, "a_hash": _hash(ta), "b_hash": _hash(tb), "same": ta == tb, "diff": "\n".join(diff),
            "a_lines": len(la), "b_lines": len(lb)}


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, timeout=TIMEOUT)


def _system_at_commit(commit: str, no: int, rows: bool, repo_root: Path) -> str:
    """커밋 시점의 build_system(no, rows) 글. 저장소 밖 임시 폴더에 worktree를 만들어 그 코드로 부른다.
    worktree에는 TO21 자료가 없어(to21/README.md만 git에 있다) to21을 repo_root/to21을 가리키는 링크로 바꾼다."""
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        raise ValueError(f"커밋 번호가 아닙니다: {commit!r}")
    repo_root = Path(repo_root)
    tmp = Path(tempfile.mkdtemp(prefix="b_app_prompt_"))
    wt = tmp / "wt"
    link = wt / "to21"
    try:
        r = _git(repo_root, "worktree", "add", "--detach", str(wt), commit)
        if r.returncode != 0:
            raise RuntimeError(f"커밋 {commit}을 꺼내지 못했습니다: {(r.stderr.strip().splitlines() or [''])[-1]}")
        if link.is_dir() and not link.is_symlink():
            shutil.rmtree(link)
        link.symlink_to(repo_root / "to21", target_is_directory=True)
        env = {**os.environ, "PYTHONPATH": str(wt / "backend" / "src"), "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([str(repo_root / "backend" / ".venv" / "bin" / "python"), "-c", _BUILD, str(no),
                            "1" if rows else "0"], cwd=wt / "backend", env=env, capture_output=True, timeout=TIMEOUT)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace").strip().splitlines() or [""]
            raise RuntimeError(f"커밋 {commit}에서 {no}항 안내문을 만들지 못했습니다: {err[-1]}")
        return r.stdout.decode("utf-8")
    finally:
        if link.is_symlink():
            link.unlink()                                 # 링크만 지운다. TO21 자료는 그대로 둔다
        try:                                              # 실패해도 git worktree remove --force와 prune으로 기록까지 지운다
            _git(repo_root, "worktree", "remove", "--force", str(wt))
            _git(repo_root, "worktree", "prune")
        except (OSError, subprocess.SubprocessError):
            pass
        shutil.rmtree(tmp, ignore_errors=True)
