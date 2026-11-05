"""줄번호 없는 쪽 글자(10/29 전처리 판)에 줄번호를 붙인 사본을 만든다 (11/04 F).

    python finetune/number_pages.py --src data/pages --dst data/pages/_numbered --docs T21-M001 T21-S016 ...
    그다음 run_sections.py ... --pages-dir ../data/pages/_numbered

왜 필요한가
- main의 run_sections.py는 실행 전에 쪽 글자 첫 줄이 `L001 …` 꼴인지 검사한다(inputs.pages_problems, 6f5ebbb9).
  새 전처리(pdf_pipeline)는 줄번호를 붙여 쓰지만, A의 학습 데이터와 개발 문서 쪽 글자(2026-10-29-wrap-mincol)는 줄번호가 없다.
- read_page_lines는 줄번호가 없으면 빈 줄을 빼고 1부터 차례로 번호를 매긴다. 이 사본도 같은 차례로 `L001 ` 꼴을 붙인다.
  그래서 모델이 받는 줄 id와 글은 원본과 똑같다(학습 데이터와 같은 입력). 확인은 --check.
- 쪽 이미지·meta.json·표 등 다른 파일은 그대로 복사한다. data/pages/ 아래라 git에 올라가지 않는다(D-47).
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

PAGE_FILE = re.compile(r"^p(\d+)\.txt$")
LINE_NO = re.compile(r"^L(\d+) (.*)$")


def number_text(text: str) -> str:
    """빈 줄을 빼고 1부터 `L001 ` 꼴을 붙인다. 이미 줄번호가 있는 쪽은 그대로 둔다."""
    rows = [l for l in text.splitlines() if l.strip()]
    if rows and all(LINE_NO.match(l) for l in rows):
        return text
    return "".join(f"L{i:03d} {l}\n" for i, l in enumerate(rows, 1))


def copy_doc(src: Path, dst: Path) -> int:
    shutil.copytree(src, dst, dirs_exist_ok=True)
    n = 0
    for p in dst.iterdir():
        if PAGE_FILE.match(p.name):
            p.write_text(number_text(p.read_text(encoding="utf-8")), encoding="utf-8")
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--dst", type=Path, required=True)
    ap.add_argument("--docs", nargs="+", required=True)
    ap.add_argument("--check", action="store_true", help="원본과 사본의 줄 id·글이 같은지 msds.extract.inputs로 확인한다(backend/src 필요)")
    a = ap.parse_args()
    for d in a.docs:
        if not (a.src / d).is_dir():
            sys.exit(f"{d}: 쪽 글자 폴더가 없습니다({a.src / d})")
        print(f"{d}: 쪽 {copy_doc(a.src / d, a.dst / d)}개")
    if a.check:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))
        from msds.extract.inputs import read_page_lines
        for d in a.docs:
            old = [(l.id, l.text) for l in read_page_lines(d, a.src)]
            new = [(l.id, l.text) for l in read_page_lines(d, a.dst)]
            print(f"{d}: 줄 {len(old)}개, {'같음' if old == new else '다름'}")
            if old != new:
                sys.exit("줄 id나 글이 달라졌습니다. 이 사본을 쓰지 않습니다")
        try:
            from msds.extract.inputs import pages_problems
            problems = pages_problems(a.docs, a.dst)
            print("실행 전 검사:", "통과" if not problems else problems)
        except ImportError:
            pass


if __name__ == "__main__":
    main()
