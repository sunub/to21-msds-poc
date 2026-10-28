"""문서 한 건 추출: 묶음별 호출 → 합치기 → 검증 → 저장 (A·B 공용, D-35, D-37).

실버(A)와 기준선(B)은 같은 코드를 쓴다. 다른 점은 두 가지뿐이다.
- mode="silver": 근거마다 적용 규칙·설명(rules, note)도 받는다 → 검수 정보 파일로 따로 저장
- mode="baseline": 검수용 요청을 뺀다 (D-37)

실행 기록은 runs/<실행 이름>/ 에 남는다.
  raw/<문서>_<묶음>.json   모델 응답 원문과 호출 정보
  log.jsonl                묶음마다 한 줄: 모델, 구조화 방식, 잘림 여부, 토큰, 걸린 시간, 오류
  validation/<문서>.json   TO21 스키마 검증 + TO21 검증기(V01~V23) 결과
  outputs/<문서>.json      합친 TO21 문서 (기준선은 여기가 최종 결과)
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import yaml

from ..checks.validator import run_to21_validator
from ..common import manifest, paths
from ..common.bundles import load_bundles
from ..common.merge import components_summary, merge_bundles
from ..common.schema import bundle_response_schema, validate_to21
from ..preprocess.render import load_pages
from .client import ChatClient, load_model_config, page_parts
from .prompt_builder import PROMPT_VERSION, load_prompt


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _log(run: Path, rec: dict) -> None:
    run.mkdir(parents=True, exist_ok=True)
    with open(run / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def save_run_config(run: Path, model_tag: str, mode: str, input_mode: str | None = None) -> None:
    """같은 설정으로 다시 돌릴 수 있도록 실행 당시 설정을 복사해 둔다. input_mode가 없으면 manifest 값을 썼다."""
    run.mkdir(parents=True, exist_ok=True)
    shutil.copy(paths.CONFIGS / "models.yaml", run / "models.yaml")
    shutil.copy(paths.CONFIGS / "bundles.yaml", run / "bundles.yaml")
    info = {"model_tag": model_tag, "mode": mode, "prompt_version": PROMPT_VERSION,
            "input_mode": input_mode or "manifest"}
    (run / "run_info.yaml").write_text(yaml.safe_dump(info, allow_unicode=True), encoding="utf-8")


def extract_document(doc_id: str, model_tag: str, mode: str, run_name: str,
                     bundle_ids: list[str] | None = None, input_mode: str | None = None) -> dict:
    assert mode in ("silver", "baseline")
    run = paths.run_dir(run_name)
    row = manifest.get(doc_id)
    cfg = load_model_config(model_tag)
    client = ChatClient(cfg)
    bundles = load_bundles()
    order = bundle_ids or list(bundles.keys())
    if "b1" not in order:
        order = ["b1"] + order       # 성분 목록이 필요하므로 b1은 항상 먼저

    pages = load_pages(doc_id)
    input_mode = input_mode or row.get("input_mode") or pages["meta"]["input_mode"]   # 인자는 입력 비교 실험용
    parts = page_parts(pages["pages"], input_mode, cfg.get("image_detail", "high"))

    responses: dict[str, dict] = {}
    comp_text = ""
    for bid in order:
        b = bundles[bid]
        system, bundle_prompt = load_prompt(bid, mode)
        schema = bundle_response_schema(b.keys, b.doc_keys, with_review=(mode == "silver"))
        intro = bundle_prompt
        if bid != "b1":
            intro += "\n\n## [성분 목록] 묶음 ①에서 뽑은 성분. comp_ref·refs는 이 번호를 쓴다\n" + comp_text
        user = [{"type": "text", "text": intro + "\n\n아래는 문서 전체 쪽이다."}] + parts

        res = client.call(system, user, schema, schema_name=f"msds_{bid}")
        # 대체 모델(fallback_models)로 한 번 더
        if not res.ok:
            for fb in cfg.get("fallback_models") or []:
                res2 = ChatClient(cfg, model=fb).call(system, user, schema, schema_name=f"msds_{bid}")
                res2.errors = res.errors + [f"→ 대체 모델 {fb} 사용"] + res2.errors
                res = res2
                if res.ok:
                    break

        _write_json(run / "raw" / f"{doc_id}_{bid}.json", {
            "doc_id": doc_id, "bundle": bid, "model": res.model, "mode": res.mode,
            "finish_reason": res.finish_reason, "usage": res.usage, "seconds": round(res.seconds, 1),
            "attempts": res.attempts, "errors": res.errors, "parsed": res.parsed, "raw_text": res.raw_text,
        })
        _log(run, {"doc_id": doc_id, "bundle": bid, "model": res.model, "structured": res.mode,
                   "finish_reason": res.finish_reason, "ok": res.ok, "attempts": res.attempts,
                   "usage": res.usage, "seconds": round(res.seconds, 1), "errors": res.errors[:3],
                   "prompt_version": PROMPT_VERSION, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        if res.parsed is not None:
            responses[bid] = res.parsed
            if bid == "b1":
                comp_text = components_summary(res.parsed)
        elif bid == "b1":
            raise RuntimeError(f"{doc_id}: 묶음 ① 실패로 중단합니다. {run / 'raw' / f'{doc_id}_b1.json'} 확인")

    doc, review_items, warnings = merge_bundles(
        responses, row, engine=f"{client.model} ({mode}, prompt {PROMPT_VERSION})",
        evidence_method=cfg.get("evidence_method", "vLM"))
    schema_errors = validate_to21(doc)
    v_results = run_to21_validator(doc)
    _write_json(run / "validation" / f"{doc_id}.json", {
        "merge_warnings": warnings,
        "missing_bundles": [b for b in order if b not in responses],
        "schema_errors": schema_errors,
        "to21_validator": v_results,
    })
    _write_json(run / "outputs" / f"{doc_id}.json", doc)
    if mode == "silver":
        _write_json(paths.silver_path(model_tag, doc_id), doc)
        _write_json(paths.silver_review_path(model_tag, doc_id), review_items)
    return {
        "doc_id": doc_id,
        "missing_bundles": [b for b in order if b not in responses],
        "schema_errors": len(schema_errors),
        "validator_errors": sum(1 for r in v_results if r["level"] == "오류"),
        "warnings": warnings,
    }
