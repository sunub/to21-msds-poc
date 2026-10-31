"""실버 추출 (역할 A, D-35·D-42·D-43·D-44·D-46)

사용법
  python scripts/run_silver.py --model gpt --docs T21-S016 T21-M013 T21-S003   # 프롬프트 시험 3건 (D-46)
  python scripts/run_silver.py --model claude --purpose 개발 --skip-done      # 같은 프롬프트로 이미 뽑은 문서는 건너뜀
  python scripts/run_silver.py --model gpt --purpose 평가 --allow-eval   # 프롬프트를 고정한 뒤에만

결과: data/silver/<model>/<문서>.json, <문서>.review.json, runs/<날짜>_silver_<model>/
"""
import argparse
import importlib.util
import json
from pathlib import Path

from _common import today
from msds.common import manifest
from msds.extract.runner import extract_document, save_run_config
from msds.common.paths import run_dir, silver_path
from msds.extract.prompt_builder import PROMPT_VERSION


def done_with_current_prompt(model_tag: str, doc_id: str) -> bool:
    """같은 프롬프트 버전으로 이미 뽑은 실버가 있으면 True. 프롬프트를 고쳐 버전을 올리면 다시 뽑는다."""
    p = silver_path(model_tag, doc_id)
    if not p.exists():
        return False
    engine = (json.loads(p.read_text(encoding="utf-8")).get("doc") or {}).get("extraction", {}).get("engine", "")
    return f"prompt {PROMPT_VERSION})" in engine


def apply_conventions_to_silver(path: Path) -> int:
    """저장된 실버의 msds 항목마다 A의 표기 규칙(conventions.apply)을 적용해 다시 쓴다. 바뀐 항목 수를 돌려준다.

    runner.py(옛 5묶음 경로)는 바꾸지 않으므로 저장 뒤에 적용한다 (ADR-022).
    """
    from msds.common import conventions
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for i, item in enumerate(data.get("msds") or []):
        new = conventions.apply(item)
        if new != item:
            data["msds"][i] = new
            changed += 1
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["gpt", "claude"])
    ap.add_argument("--docs", nargs="*")
    ap.add_argument("--purpose", choices=manifest.PURPOSES)
    ap.add_argument("--bundles", nargs="*", help="예: b1 b2 (기본: 전부)")
    ap.add_argument("--run-name")
    ap.add_argument("--allow-eval", action="store_true",
                    help="평가용 문서 실행 허용. 프롬프트를 고정한 뒤에만 쓴다 (D-43)")
    ap.add_argument("--skip-done", action="store_true",
                    help="현재 프롬프트 버전으로 이미 뽑은 문서는 건너뛴다 (시험 3건 재사용, D-46)")
    a = ap.parse_args()
    targets = manifest.select(a.purpose, a.docs)
    if not targets:
        ap.error("대상 문서가 없습니다")
    if any(r["purpose"] == "평가" for r in targets) and not a.allow_eval:
        ap.error("평가용 문서가 들어 있습니다. 프롬프트를 고정했다면 --allow-eval을 붙이세요 (D-43)")
    run_name = a.run_name or f"{today()}_silver_{a.model}"
    save_run_config(run_dir(run_name), a.model, "silver")
    has_conventions = importlib.util.find_spec("msds.common.conventions") is not None
    if not has_conventions:
        print("표기 규칙 함수 없음")
    for r in targets:
        if a.skip_done and not a.bundles and done_with_current_prompt(a.model, r["doc_id"]):
            print(f"[건너뜀] {r['doc_id']}: 프롬프트 {PROMPT_VERSION}로 이미 뽑음")
            continue
        try:
            res = extract_document(r["doc_id"], a.model, "silver", run_name, a.bundles)
            line = json.dumps(res, ensure_ascii=False)
            if has_conventions:
                line += f" 표기 규칙 적용: {apply_conventions_to_silver(silver_path(a.model, r['doc_id']))}건 바뀜"
            print(line)
        except Exception as e:   # 한 문서가 실패해도 나머지는 계속
            print(f"[실패] {r['doc_id']}: {e}")
    print(f"기록: runs/{run_name}/log.jsonl")
