"""항목별 추출 (역할 B, 재계획 10/28): 문서 여러 건 × 모델 하나. 문서는 한 번에 하나씩 처리한다.

사용법
  python scripts/run_sections.py --model qwen3_30b_a3b_rngd --docs T21-S003 T21-S016 T21-M013
  python scripts/run_sections.py --model qwen36_35b_runpod --purpose 개발 --workers 8
  python scripts/run_sections.py --model qwen3_30b_a3b_rngd --docs T21-025 --allow-eval   # 프롬프트 고정 후 (D-43)
  python scripts/run_sections.py --model qwen3_30b_a3b_rngd --docs T21-M013 --pages-dir ../data/pages/version9   # 실행 입력은 version9 (ADR-018)
  python scripts/run_sections.py --model qwen36_35b_runpod --all-in-pages-dir --pages-dir ../data/pages   # manifest 밖 신규 40건 (format40)
manifest에 없는 문서 번호는 <pages-dir>/<번호>/meta.json이 있으면 그 파일로 문서 정보를 만든다.

결과: runs/<날짜>_sections_<모델 태그>/outputs/<문서>.json, checks/, raw/, timing.jsonl, run_info.yaml
"""
import argparse
import json
from pathlib import Path

from _common import today
from msds.common import manifest
from msds.common.paths import PAGES, run_dir
from msds.extract.inputs import pages_problems
from msds.extract.section_runner import doc_meta_from_pages, run_document, save_run_info


def select_docs(doc_ids: list[str] | None, purpose: str | None, allow_eval: bool) -> list[dict]:
    """manifest에서 대상 문서를 고른다. 평가용 문서는 allow_eval 없이는 거부한다 (D-43)."""
    return _check_targets(manifest.select(purpose, doc_ids), allow_eval)


def select_targets(doc_ids: list[str] | None, purpose: str | None, allow_eval: bool, pages_dir: Path = PAGES,
                   all_in_pages_dir: bool = False) -> list[dict]:
    """select_docs에 manifest 밖 문서를 더한다 (format40). manifest에 없는 번호는 <pages_dir>/<번호>/meta.json의
    dict(doc_meta_from_pages)를 쓰고, 그 파일도 없으면 KeyError. all_in_pages_dir면 doc_ids·purpose 없이
    pages_dir 아래 meta.json이 있는 폴더 전부를 문서 번호 순으로 고른다(manifest에 있는 번호는 manifest 행).
    manifest 밖 문서는 평가용이 아닌 것으로 본다(C가 manifest와 겹치지 않게 골랐다).
    manifest의 평가용 문서가 섞이면 allow_eval 없이는 거부한다 (D-43)."""
    if all_in_pages_dir:
        if doc_ids or purpose:
            raise ValueError("--all-in-pages-dir는 --docs·--purpose와 같이 쓰지 않습니다")
        doc_ids = sorted(p.parent.name for p in Path(pages_dir).glob("*/meta.json"))
        if not doc_ids:
            raise ValueError(f"meta.json이 있는 문서 폴더가 없습니다: {pages_dir}")
    if not doc_ids:
        return select_docs(None, purpose, allow_eval)
    known = {r["doc_id"] for r in manifest.load()}
    outside = {d: doc_meta_from_pages(d, pages_dir) for d in doc_ids if d not in known}
    missing = sorted(d for d, row in outside.items() if row is None)
    if missing:
        raise KeyError(f"manifest에 없고 쪽 글자 폴더에 meta.json도 없는 문서 번호: {missing}")
    inside = [d for d in doc_ids if d in known]
    targets = manifest.select(purpose, inside) if inside else []
    targets += [row for row in outside.values() if not purpose or row["purpose"] == purpose]
    if all_in_pages_dir:
        targets.sort(key=lambda r: r["doc_id"])
    return _check_targets(targets, allow_eval)


def _check_targets(targets: list[dict], allow_eval: bool) -> list[dict]:
    if not targets:
        raise ValueError("대상 문서가 없습니다")
    evals = [r["doc_id"] for r in targets if r["purpose"] == "평가"]
    if evals and not allow_eval:
        raise ValueError(f"평가용 문서가 들어 있습니다({', '.join(evals)}). "
                         "프롬프트를 고정했다면 --allow-eval을 붙이세요 (D-43)")
    return targets


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="법정 16개 항목별로 모델을 동시에 불러 TO21 v0.6 JSON을 만든다")
    ap.add_argument("--model", required=True, help="configs/models.yaml의 태그")
    ap.add_argument("--docs", nargs="*")
    ap.add_argument("--purpose", choices=manifest.PURPOSES)
    ap.add_argument("--run-name")
    ap.add_argument("--allow-eval", action="store_true", help="평가용 문서 실행 허용 (D-43)")
    ap.add_argument("--workers", type=int, help="항목별 동시 호출 수 (없으면 models.yaml의 concurrency)")
    ap.add_argument("--pages-dir", type=Path, default=PAGES, help="쪽 글자 폴더 (없으면 data/pages)")
    ap.add_argument("--all-in-pages-dir", action="store_true",
                    help="--docs·--purpose 없이 쪽 글자 폴더 아래 meta.json이 있는 문서를 모두 돌린다 (format40)")
    a = ap.parse_args()
    try:
        targets = select_targets(a.docs, a.purpose, a.allow_eval, a.pages_dir, a.all_in_pages_dir)
    except (KeyError, ValueError) as e:
        ap.error(e.args[0])
    problems = pages_problems([r["doc_id"] for r in targets], a.pages_dir)
    if problems:
        ap.error(f"쪽 글자 폴더를 확인하세요({a.pages_dir}). " + "; ".join(problems))
    run_name = a.run_name or f"{today()}_sections_{a.model}"
    save_run_info(run_dir(run_name), a.model, a.pages_dir, max_workers=a.workers)
    for r in targets:
        try:
            res = run_document(r["doc_id"], a.model, run_name, max_workers=a.workers, pages_dir=a.pages_dir)
            print(json.dumps(res, ensure_ascii=False))
        except Exception as e:
            print(f"[실패] {r['doc_id']}: {e}")
    print(f"기록: runs/{run_name}/")
