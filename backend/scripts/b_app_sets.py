"""작업 화면의 문서 묶음: data/pages 아래의 판을 찾고 고를 수 있는지 판정한다 (역할 B, 개발 전용, ADR-028).

묶음은 문서 폴더(pNNN.txt가 바로 안에 있는 폴더)를 바로 아래에 가진 폴더다. 예: data/pages/prev/version9.
- 후보는 pages_root 자신과 그 아래 두 단계 폴더다. 문서 폴더와 그 안(tables/ 등)은 후보가 아니다.
- 평가용 문서는 폴더 안의 어떤 파일도 열지 않는다. 문서 번호와 잠긴 이유만 둔다 (D-43).
- 요청에서 받은 묶음 id로 경로를 만들지 않는다. find_set으로 목록에 있는 id인지 먼저 본다.
- 화면에 보일 글은 b_app_text에 있다.
"""
import json
import re
from pathlib import Path

import _common  # noqa: F401  src 경로 등록
import b_app_text as bt
from msds.common import manifest
from msds.extract.inputs import _LINE_NO, _PAGE_FILE

DOC_ID = re.compile(r"^[A-Z][A-Z0-9]*-[A-Z0-9]+$")   # T21-S003, RAW-01. 요청에서 받은 문서 번호는 이것으로 먼저 거른다(경로 탈출 막기)
DEFAULT_SET = "prev/version9"
_GROUPS = {"개발": "dev", "평가": "eval"}            # manifest의 그 밖 용도(기타)는 other
_COUNT_KEYS = {"dev": "dev", "eval": "eval_locked", "other": "other", "outside": "outside", "unknown": "unknown"}
_LOCKS = {"eval": "eval_locked", "unknown": "unknown_doc"}


def is_doc_dir(path: Path) -> bool:
    """pNNN.txt가 하나라도 바로 안에 있는 폴더. 파일 이름만 본다."""
    return any(_PAGE_FILE.match(p.name) for p in path.iterdir())


def _page_files(doc_dir: Path) -> list[tuple[int, Path]]:
    return sorted((int(m.group(1)), p) for p in doc_dir.iterdir() if (m := _PAGE_FILE.match(p.name)))


def _meta_doc_id(doc_dir: Path) -> str | None:
    try:
        meta = json.loads((doc_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta.get("doc_id") if isinstance(meta, dict) else None


def _group(doc_id: str, doc_dir: Path | None, rows: list[dict]) -> str:
    """manifest에 있으면 그 용도, 없으면 meta.json의 doc_id가 폴더 이름과 같을 때만 outside."""
    if not DOC_ID.fullmatch(doc_id):
        return "unknown"
    row = next((r for r in rows if r["doc_id"] == doc_id), None)
    if row is not None:
        return _GROUPS.get(row.get("purpose"), "other")
    return "outside" if doc_dir is not None and _meta_doc_id(doc_dir) == doc_id else "unknown"


def _first_line_numbered(path: Path) -> bool:
    """첫 비어 있지 않은 줄이 `L001 ` 꼴인가 (inputs.read_page_lines와 같은 규칙)."""
    with open(path, encoding="utf-8") as f:
        for raw in f:
            if raw.strip():
                return bool(_LINE_NO.match(raw.rstrip("\r\n")))
    return False


def doc_lock(doc_id: str, doc_dir: Path | None, rows: list[dict]) -> str | None:
    """잠근 이유 또는 None. 평가용과 용도를 확인할 수 없는 문서를 잠근다 (D-43)."""
    key = _LOCKS.get(_group(doc_id, doc_dir, rows))
    return bt.SET_TEXT[key] if key else None


def doc_entry(doc_dir: Path, rows: list[dict]) -> dict:
    """{"doc_id", "group", "locked", "reason", "pages", "line_numbers"}. 잠긴 문서는 파일을 열지 않는다(이름만 센다)."""
    doc_id = doc_dir.name
    group = _group(doc_id, doc_dir, rows)
    key = _LOCKS.get(group)
    files = _page_files(doc_dir)
    numbered = None if key else bool(files) and _first_line_numbered(files[0][1])
    return {"doc_id": doc_id, "group": group, "locked": key is not None, "reason": bt.SET_TEXT[key] if key else None,
            "pages": len(files), "line_numbers": numbered}


def _subdirs(path: Path) -> list[Path]:
    return sorted(p for p in path.iterdir() if p.is_dir())


def _unusable_reason(docs: list[dict]) -> str | None:
    if not docs:
        return "empty"
    if any(not d["locked"] and d["line_numbers"] for d in docs):
        return None
    if all(d["group"] == "eval" for d in docs):
        return "eval_only"
    if all(d["locked"] for d in docs):
        return "nothing_open"
    return "no_line_numbers"


def _set_entry(folder: Path, docs: list[dict], pages_root: Path) -> dict:
    set_id = folder.relative_to(pages_root).as_posix()
    reason = _unusable_reason(docs)
    counts = dict.fromkeys(_COUNT_KEYS.values(), 0)
    for d in docs:
        counts[_COUNT_KEYS[d["group"]]] += 1
    return {"id": set_id, "label": bt.set_label(set_id), "path": folder.relative_to(pages_root.parent.parent).as_posix(),
            "usable": reason is None, "reason": bt.SET_TEXT[reason] if reason else None, "counts": counts,
            "docs": sorted(docs, key=lambda d: d["doc_id"])}


def list_sets(pages_root: Path, rows: list[dict] | None = None) -> list[dict]:
    """pages_root 아래의 묶음 목록(id 순). 빈 폴더는 고를 수 없는 묶음으로 넣고, 묶음을 담기만 하는 폴더는 뺀다."""
    if not pages_root.is_dir():
        return []
    rows = manifest.load() if rows is None else rows
    level1 = [p for p in _subdirs(pages_root) if not is_doc_dir(p)]
    level2 = [p for d in level1 for p in _subdirs(d) if not is_doc_dir(p)]
    sets = []
    for folder in [pages_root, *level1, *level2]:
        children = _subdirs(folder)
        doc_dirs = [p for p in children if is_doc_dir(p)]
        if doc_dirs or not children:
            sets.append(_set_entry(folder, [doc_entry(p, rows) for p in doc_dirs], pages_root))
    return sorted(sets, key=lambda s: s["id"])


def find_set(sets: list[dict], set_id) -> dict | None:
    """목록에 있는 id의 묶음. "../x", 절대 경로, 없는 id는 None."""
    return next((s for s in sets if s["id"] == set_id), None)


def has_doc(s: dict, doc_id: str) -> bool:
    """그 묶음에 문서가 잠기지 않은 채 들어 있는가."""
    return any(d["doc_id"] == doc_id and not d["locked"] for d in s["docs"])


def resolve_run_set(recorded: str | None, doc_id: str, sets: list[dict]) -> tuple[str | None, str]:
    """(묶음 id, source). recorded는 run_info.yaml의 pages_dir(저장소 기준, 예 "data/pages/version9")다.
    기록대로의 묶음이 있으면 "run", 10/30 배치 변경으로 prev/ 아래로 옮겨진 묶음이면 "moved", 못 찾으면 (None, "none").
    쓸 수 없는 묶음(줄 번호 없는 판)도 돌려준다. 지난 실행을 그때 입력 그대로 보여 주기 위해서다."""
    if not recorded:
        return None, "none"
    rel = str(recorded).replace("\\", "/")
    while rel.startswith(("./", "../")):
        rel = rel.split("/", 1)[1]
    parts = [p for p in rel.split("/") if p]
    if parts[:2] != ["data", "pages"]:
        return None, "none"
    rest = "/".join(parts[2:]) or "."
    for set_id, source in ((rest, "run"), ("prev" if rest == "." else f"prev/{rest}", "moved")):
        s = find_set(sets, set_id)
        if s is not None and has_doc(s, doc_id):
            return set_id, source
    return None, "none"


def set_dir(pages_root: Path, set_id: str) -> Path:
    """묶음 폴더. set_id는 find_set으로 확인한 목록의 id만 넘긴다."""
    return pages_root / set_id


def default_set(sets: list[dict], startup_dir: Path | None, pages_root: Path) -> str | None:
    """켤 때 받은 폴더(--pages-dir) → DEFAULT_SET → 첫 번째 쓸 수 있는 묶음 순. 쓸 수 있는 묶음이 없으면 None."""
    usable = [s["id"] for s in sets if s["usable"]]
    if startup_dir is not None:
        here = Path(startup_dir).resolve()
        found = next((sid for sid in usable if set_dir(pages_root, sid).resolve() == here), None)
        if found:
            return found
    if DEFAULT_SET in usable:
        return DEFAULT_SET
    return usable[0] if usable else None
