"""런타임 폴더가 개발 전용 폴더를 import하지 못하게 막는다.

폐쇄망에는 런타임 폴더만 반입한다. 의존 방향은 개발 전용 -> 런타임만 허용한다.
"""
import ast
from pathlib import Path

MSDS = Path(__file__).resolve().parents[1] / "src" / "msds"

RUNTIME = ["common", "preprocess", "extract", "checks", "compliance", "api"]
DEV_ONLY = {"review", "evaluate"}


def imported_packages(path: Path, root: Path = MSDS):
    """파일이 import하는 msds 바로 아래 패키지 이름을 돌려준다 (절대·상대 import 모두)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "msds" and len(parts) > 1:
                    yield parts[1]
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".") if node.module else []
            if node.level == 0:
                if module[:1] == ["msds"] and len(module) > 1:
                    yield module[1]
                continue
            # 상대 import: 파일 위치에서 level-1 단계 올라간 폴더를 기준으로 푼다
            base = path.parent
            for _ in range(node.level - 1):
                base = base.parent
            try:
                resolved = list(base.relative_to(root).parts) + module
            except ValueError:
                continue
            if resolved:
                yield resolved[0]
            else:  # from .. import review
                yield from (alias.name for alias in node.names)


def violations_in(root: Path):
    found = []
    for pkg in RUNTIME:
        for path in (root / pkg).rglob("*.py"):
            bad = DEV_ONLY & set(imported_packages(path, root))
            if bad:
                found.append(f"{path.relative_to(root)} -> {sorted(bad)}")
    return found


def test_runtime_does_not_import_dev_only():
    found = violations_in(MSDS)
    assert not found, "런타임이 개발 전용 폴더를 import함:\n" + "\n".join(found)


def test_detects_absolute_and_relative_imports(tmp_path):
    """검사 자체가 동작하는지 확인한다: 위반을 일부러 만들어 잡히는지 본다."""
    (tmp_path / "extract").mkdir()
    (tmp_path / "checks").mkdir()
    (tmp_path / "extract" / "a.py").write_text("from msds.review import x\n")
    (tmp_path / "checks" / "b.py").write_text("from ..evaluate import y\n")
    (tmp_path / "checks" / "c.py").write_text("from .. import review\n")
    (tmp_path / "checks" / "ok.py").write_text("from ..common import z\nfrom . import d\n")
    found = violations_in(tmp_path)
    assert len(found) == 3, found
