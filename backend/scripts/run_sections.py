"""항목별 추출 (역할 B, 재계획 10/28): 문서 여러 건 × 모델 하나. 문서는 한 번에 하나씩 처리한다.

사용법
  python scripts/run_sections.py --model qwen3_30b_a3b_rngd --docs T21-S003 T21-S016 T21-M013
  python scripts/run_sections.py --model qwen36_35b_runpod --purpose 개발 --workers 8
  python scripts/run_sections.py --model qwen3_30b_a3b_rngd --docs T21-025 --allow-eval   # 프롬프트 고정 후 (D-43)
  python scripts/run_sections.py --model qwen3_30b_a3b_rngd --docs T21-M013 --pages-dir ../data/pages/chars_wrap

결과: runs/<날짜>_sections_<모델 태그>/outputs/<문서>.json, checks/, raw/, timing.jsonl, run_info.yaml
"""
import argparse
import json
from pathlib import Path

from _common import today
from msds.common import manifest
from msds.common.paths import PAGES, run_dir
from msds.extract.section_runner import run_document, save_run_info


def select_docs(doc_ids: list[str] | None, purpose: str | None, allow_eval: bool) -> list[dict]:
    """manifest에서 대상 문서를 고른다. 평가용 문서는 allow_eval 없이는 거부한다 (D-43)."""
    targets = manifest.select(purpose, doc_ids)
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
    a = ap.parse_args()
    try:
        targets = select_docs(a.docs, a.purpose, a.allow_eval)
    except (KeyError, ValueError) as e:
        ap.error(e.args[0])
    run_name = a.run_name or f"{today()}_sections_{a.model}"
    save_run_info(run_dir(run_name), a.model, a.pages_dir, max_workers=a.workers)
    for r in targets:
        try:
            res = run_document(r["doc_id"], a.model, run_name, max_workers=a.workers, pages_dir=a.pages_dir)
            print(json.dumps(res, ensure_ascii=False))
        except Exception as e:
            print(f"[실패] {r['doc_id']}: {e}")
    print(f"기록: runs/{run_name}/")
