"""기준선 추출 (역할 B, D-37·D-43·D-44·D-46): Colab vLLM의 Qwen3.8-27B(FP8), 실버와 같은 프롬프트·묶음·입력

사용법
  python scripts/run_baseline.py --docs T21-S016 T21-M013 T21-S003   # 프롬프트 시험 3건 (D-46)
  python scripts/run_baseline.py --purpose 개발
  python scripts/run_baseline.py --purpose 개발 --run-name 20261026_baseline_qwen38 --skip-done   # 세션이 끊긴 뒤 이어 돌리기
  python scripts/run_baseline.py --docs T21-025 --allow-eval     # 프롬프트 고정 후 25번 (10/27 보고)

결과: runs/<날짜>_baseline_qwen38/outputs/<문서>.json
"""
import argparse
import json

from _common import today
from msds.common import manifest
from msds.extract.runner import extract_document, save_run_config
from msds.common.paths import run_dir
from msds.extract.prompt_builder import PROMPT_VERSION


def done_with_current_prompt(run_name: str, doc_id: str) -> bool:
    """이번 실행 폴더에 같은 프롬프트 버전으로 뽑은 outputs/<doc_id>.json이 있으면 True."""
    p = run_dir(run_name) / "outputs" / f"{doc_id}.json"
    if not p.exists():
        return False
    engine = (json.loads(p.read_text(encoding="utf-8")).get("doc") or {}).get("extraction", {}).get("engine", "")
    return f"prompt {PROMPT_VERSION})" in engine


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen38")
    ap.add_argument("--docs", nargs="*")
    ap.add_argument("--purpose", choices=manifest.PURPOSES)
    ap.add_argument("--bundles", nargs="*")
    ap.add_argument("--run-name")
    ap.add_argument("--allow-eval", action="store_true", help="평가용 문서 실행 허용 (D-43)")
    ap.add_argument("--skip-done", action="store_true",
                    help="세션이 끊긴 뒤 이어 돌리기: 이번 실행 폴더에 같은 프롬프트 버전 결과가 있는 문서는 건너뛴다")
    a = ap.parse_args(argv)
    targets = manifest.select(a.purpose, a.docs)
    if not targets:
        ap.error("대상 문서가 없습니다")
    if any(r["purpose"] == "평가" for r in targets) and not a.allow_eval:
        ap.error("평가용 문서가 들어 있습니다. 프롬프트를 고정했다면 --allow-eval을 붙이세요 (D-43)")
    run_name = a.run_name or f"{today()}_baseline_{a.model}"
    save_run_config(run_dir(run_name), a.model, "baseline")
    for r in targets:
        if a.skip_done and not a.bundles and done_with_current_prompt(run_name, r["doc_id"]):
            print(f"[건너뜀] {r['doc_id']}: 같은 프롬프트({PROMPT_VERSION}) 결과가 있음")
            continue
        try:
            res = extract_document(r["doc_id"], a.model, "baseline", run_name, a.bundles)
            print(json.dumps(res, ensure_ascii=False))
        except Exception as e:
            print(f"[실패] {r['doc_id']}: {e}")
    print(f"기록: runs/{run_name}/log.jsonl")


if __name__ == "__main__":
    main()
