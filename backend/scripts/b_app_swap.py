"""작업 화면의 자료 바꾸기: 받은 문서 폴더를 검사해 data/pages로 가져오고, 새 정답(data/gold)이 왔는지 알린다 (역할 B, 개발 전용).

- 검사(inspect)는 파일을 옮기지 않는다. 적용(apply)만 복사한다. 앱에 같은 이름의 다른 폴더가 있으면 덮어쓰지 않는다.
- 평가용 문서와 원본이 같은 문서는 복사만 하고 쪽 글자를 열지 않는다. 정답도 평가용은 파일 이름만 센다 (D-43).
- data/pages는 git에 올리지 않는 폴더다 (D-47). 복사는 임시 폴더에 끝낸 뒤 이름을 바꿔, 중간 상태가 묶음으로 보이지 않게 한다.
- 정답 파일을 받는 일은 사람이 git으로 한다. 여기서는 읽기와 fetch만 한다. 정답 파일을 열지 않고 이름만 쓴다.
- 화면에 보일 글은 b_app_text의 UI_TEXT["swap"]에 있다.
"""
import filecmp
import os
import re
import shlex
import shutil
import subprocess
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

import _common  # noqa: F401  src 경로 등록
import b_app_sets as bsets
from msds.common import manifest

_NAME = re.compile(r"\w[\w.\- ]*")                   # 묶음 id가 되는 폴더 이름. 경로 문자와 숨김 폴더를 막는다
_RESERVED = {"prev"}                                 # data/pages/prev는 옛 판을 모으는 폴더다
_SKIP = (".DS_Store", "__MACOSX")                    # 맥이 만드는 파일. 복사와 비교에서 뺀다
_SHA = re.compile(r"[0-9a-f]{7,40}")
_COPY_LOCK = threading.Lock()                        # 같은 폴더를 두 번 눌러도 복사는 한 번씩
_MAIN = "main"
GIT_TIMEOUT = 10
FETCH_TIMEOUT = 20


class SwapProblem(ValueError):
    """화면에 이유와 할 일을 보일 문제. 글은 b_app_text.swap_problem(kind, **facts)에 있다."""

    def __init__(self, kind: str, **facts):
        self.kind, self.facts = kind, facts
        super().__init__(kind)


def _nfc(text) -> str:
    """맥의 파일 이름은 자모가 나뉘어 있을 수 있다. 화면과 비교에는 합친 글자를 쓴다."""
    return unicodedata.normalize("NFC", text or "")


def _doc_dirs(folder: Path) -> list[Path]:
    return [p for p in bsets._subdirs(folder) if bsets.is_doc_dir(p)]


def _set_name(set_id: str) -> str:
    return _nfc(set_id.rsplit("/", 1)[-1])


def candidates(downloads: Path, pages_root: Path) -> dict:
    """downloads 바로 아래의 문서 폴더(문서 폴더를 바로 안에 가진 폴더). 최근 것부터. 읽지 못하면 error만 채운다."""
    found = {"folder": str(downloads), "items": [], "error": None}
    try:
        folders = bsets._subdirs(downloads)
    except OSError:
        return {**found, "error": "unreadable"}
    in_app = {_set_name(s["id"]) for s in bsets.list_sets(pages_root) if s["docs"]}
    items = []
    for folder in folders:
        try:
            docs, mtime = len(_doc_dirs(folder)), folder.stat().st_mtime
        except OSError:                              # 권한 없는 폴더 하나 때문에 목록을 잃지 않는다
            continue
        if docs:
            items.append((mtime, {"name": _nfc(folder.name), "path": str(folder), "docs": docs,
                                  "modified_at": datetime.fromtimestamp(mtime).astimezone().isoformat(timespec="seconds"),
                                  "in_app": _nfc(folder.name) in in_app}))
    items.sort(key=lambda pair: pair[0], reverse=True)
    return {**found, "items": [item for _, item in items]}


def _checked_folder(path) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise SwapProblem("swap_no_path", path=str(path or ""))
    folder = Path(path.strip()).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise SwapProblem("swap_no_path", path=path)
    return folder


def _inside(folder: Path, pages_root: Path) -> str | None:
    """folder가 pages_root 안이면 그 묶음 id."""
    root, here = pages_root.resolve(), folder.resolve()
    return here.relative_to(root).as_posix() if here == root or root in here.parents else None


def _files(folder: Path) -> dict[str, Path]:
    return {_nfc(p.relative_to(folder).as_posix()): p for p in folder.rglob("*")
            if p.is_file() and not set(p.relative_to(folder).parts) & set(_SKIP)}


def _same_files(a: Path, b: Path, locked: set[str]) -> bool:
    """파일 목록과 크기가 같고, 잠기지 않은 문서는 내용까지 같은가. 잠긴 문서는 크기만 본다 (D-43)."""
    left, right = _files(a), _files(b)
    if left.keys() != right.keys():
        return False
    for rel, path in left.items():
        if path.stat().st_size != right[rel].stat().st_size:
            return False
        if rel.split("/", 1)[0] not in locked and not filecmp.cmp(path, right[rel], shallow=False):
            return False
    return True


def _existing(folder: Path, name: str, pages_root: Path, sets: list[dict], locked: set[str]) -> dict:
    """앱에 이 폴더가 이미 있는가: new(없음), same(내용이 같음), different(이름만 같음)."""
    inside = _inside(folder, pages_root)
    if inside is not None:
        return {"state": "same", "set_id": inside}
    named = [s["id"] for s in sets if s["docs"] and _set_name(s["id"]) == name]
    same = next((i for i in named if _same_files(folder, bsets.set_dir(pages_root, i), locked)), None)
    if same is not None:
        return {"state": "same", "set_id": same}
    return {"state": "different", "set_id": named[0]} if named else {"state": "new", "set_id": None}


def _gold_docs(gold_root: Path, purposes: dict[str, str]) -> set[str]:
    """평가용이 아닌 정답의 문서 번호. 파일 이름만 본다."""
    if not gold_root.is_dir():
        return set()
    names = (m.group(1) for p in gold_root.iterdir() if (m := bsets.KEY_FILE.fullmatch(p.name)))
    return {d for d in names if purposes.get(d) != "평가"}


def _alternative(sets: list[dict], gold: set[str]) -> dict | None:
    """정답과 가장 많이 겹치는 묶음. 옛 판 모음(prev/)보다 바로 아래 묶음을 먼저 권한다."""
    overlap = [(sum(not d["locked"] and d["doc_id"] in gold for d in s["docs"]), not s["id"].startswith("prev"), s["id"])
               for s in sets if s["usable"]]
    best = max(overlap, default=None)
    return {"id": best[2], "docs": best[0]} if best and best[0] else None


def _eval_twin(doc_dir: Path, rows: list[dict]) -> str | None:
    """원본 PDF가 같은 평가 문서의 번호."""
    source = _nfc(bsets._read_meta(doc_dir).get("source_file"))
    return next((r["doc_id"] for r in rows if r.get("purpose") == "평가" and _nfc(r.get("source_file")) == source), None)


def inspect(path, pages_root: Path, gold_root: Path, rows: list[dict] | None = None) -> dict:
    """받은 폴더를 파일을 옮기지 않고 검사한다. verdict는 score(점수도 나옴), format_only(양식만 확인), unusable(시험 불가)."""
    rows = manifest.load() if rows is None else rows
    pages_root, gold_root = Path(pages_root), Path(gold_root)
    folder = _checked_folder(path)
    name = _nfc(folder.name)
    if bsets.is_doc_dir(folder):
        raise SwapProblem("swap_doc_folder", name=name)
    if _inside(folder, pages_root) is None and (not _NAME.fullmatch(name) or name in _RESERVED):
        raise SwapProblem("swap_bad_name", name=name)
    doc_dirs = _doc_dirs(folder)
    if not doc_dirs:
        raise SwapProblem("swap_no_docs", name=name)
    docs = [bsets.doc_entry(p, rows) for p in doc_dirs]
    open_docs = [d for d in docs if not d["locked"]]
    purposes = {r["doc_id"]: r.get("purpose") for r in rows}
    gold = _gold_docs(gold_root, purposes)
    runnable = [d for d in open_docs if bsets.job_check(d, "run") is None]
    score = sum(d["doc_id"] in gold for d in runnable)
    same_as = {p.name: twin for p, d in zip(doc_dirs, docs)
               if d["group"] == "eval" and p.name not in purposes and (twin := _eval_twin(p, rows))}
    sets = bsets.list_sets(pages_root, rows)
    existing = _existing(folder, name, pages_root, sets, {d["doc_id"] for d in docs if d["locked"]})
    return {"name": name, "path": str(folder), "docs_total": len(docs),
            "verdict": "score" if score else "format_only" if runnable else "unusable",
            "score_docs": score, "gold_docs": len(gold),
            "batch_docs": len(runnable), "try_docs": sum(bsets.job_check(d, "try") is None for d in open_docs),
            "no_line_numbers": sum(not d["line_numbers"] for d in open_docs),
            "locked": {"eval": sum(d["group"] == "eval" for d in docs),
                       "unknown": sum(d["locked"] and d["group"] != "eval" for d in docs), "same_as": same_as},
            "existing": existing, "target": f"data/pages/{existing['set_id'] or name}",
            "score_alternative": None if score else _alternative(sets, gold)}


def _copy(folder: Path, target: Path) -> None:
    """임시 폴더에 다 복사한 뒤 이름을 바꾼다. 실패하면 아무것도 남기지 않는다. 빈 자리 폴더만 대신한다(rmdir)."""
    temp = target.parent / f".{target.name}.copying"
    shutil.rmtree(temp, ignore_errors=True)
    try:
        shutil.copytree(folder, temp, ignore=shutil.ignore_patterns(*_SKIP))
        if target.exists():
            (target / ".DS_Store").unlink(missing_ok=True)
            target.rmdir()
        os.rename(temp, target)
    except OSError as e:
        shutil.rmtree(temp, ignore_errors=True)
        raise SwapProblem("swap_copy_failed", detail=str(e)) from e


def apply(path, pages_root: Path, gold_root: Path, rows: list[dict] | None = None) -> dict:
    """{"set_id", "copied"}. 앱에 같은 폴더가 있으면 복사하지 않고 그 묶음을 돌려준다."""
    with _COPY_LOCK:
        info = inspect(path, pages_root, gold_root, rows)
        state, name = info["existing"]["state"], info["name"]
        if info["verdict"] == "unusable":
            raise SwapProblem("swap_unusable", name=name)
        if state == "different":
            raise SwapProblem("swap_conflict", name=name, target=info["target"])
        if state == "same":
            return {"set_id": info["existing"]["set_id"], "copied": False}
        _copy(Path(info["path"]), Path(pages_root) / name)
        return {"set_id": name, "copied": True}


# ── 정답(골드) ───────────────────────────────────────────

def _git(repo: Path, *args, timeout: int = GIT_TIMEOUT) -> str | None:
    """git 출력 또는 None(저장소가 아니거나 실패). 비밀번호를 묻느라 멈추지 않게 한다."""
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _by_doc(names: list[str], purposes: dict[str, str]) -> dict:
    """파일 이름들을 개발 문서 번호와 평가 문서 건수로 나눈다. 평가 문서 번호는 돌려주지 않는다."""
    docs = [m.group(1) for n in names if (m := bsets.KEY_FILE.fullmatch(Path(n).name))]
    return {"dev": sorted(d for d in docs if purposes.get(d) != "평가"), "eval": sum(purposes.get(d) == "평가" for d in docs)}


def _changed_files(repo: Path, spec: list[str], rel: str) -> list[str]:
    return (_git(repo, "diff", "--name-only", *spec, "--", rel) or "").splitlines()


def gold_status(gold_root: Path, repo_root: Path, rows: list[dict] | None = None, *, fetch: bool = False,
                since: str | None = None) -> dict:
    """받아 둔 정답의 건수와 최근 커밋, origin/main에 더 새 정답이 있는지, since 커밋 뒤로 바뀐 정답.
    fetch가 참일 때만 네트워크를 부른다. fetched는 True(성공), False(실패), None(안 함)."""
    rows = manifest.load() if rows is None else rows
    gold_root, repo_root = Path(gold_root), Path(repo_root)
    purposes = {r["doc_id"]: r.get("purpose") for r in rows}
    counts = _by_doc([p.name for p in gold_root.iterdir()] if gold_root.is_dir() else [], purposes)
    try:
        rel = gold_root.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = gold_root.as_posix()
    out = {"path": rel, "docs": len(counts["dev"]), "eval_docs": counts["eval"], "commit": None, "branch": None,
           "fetched": None, "behind": {"dev": [], "eval": 0}, "changed": None, "pull": None}
    branch = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch is None:
        return {**out, "fetched": False if fetch else None}
    log = _git(repo_root, "log", "-1", "--format=%h%x09%cI", "--", rel)
    if log:
        sha, _, at = log.partition("\t")
        out["commit"] = {"sha": sha, "at": at}
    if fetch:
        out["fetched"] = _git(repo_root, "fetch", "--quiet", "origin", _MAIN, timeout=FETCH_TIMEOUT) is not None
    root = shlex.quote(str(repo_root))
    out.update(branch=branch, pull=f"git -C {root} pull" if branch == _MAIN else f"git -C {root} merge origin/{_MAIN}",
               behind=_by_doc(_changed_files(repo_root, [f"HEAD...origin/{_MAIN}"], rel), purposes))
    if since and _SHA.fullmatch(since) and _git(repo_root, "cat-file", "-e", f"{since}^{{commit}}") is not None:
        out["changed"] = _by_doc(_changed_files(repo_root, [since, "HEAD"], rel), purposes)
    return out
