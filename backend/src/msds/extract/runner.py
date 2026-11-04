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
import re
import shutil
import time
from pathlib import Path

import yaml

from ..checks.validator import run_to21_validator
from ..common import manifest, paths
from ..common.bundles import load_bundles
from ..common.merge import components_summary, merge_bundles
from ..common.schema import bundle_response_schema, validate_to21
from ..preprocess.render import PREPROCESS_VERSION, load_pages
from .client import ChatClient, load_model_config, page_parts
from .prompt_builder import PROMPT_VERSION, load_prompt


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _log(run: Path, rec: dict) -> None:
    run.mkdir(parents=True, exist_ok=True)
    with open(run / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def parse_pages(spec: str) -> list[int]:
    """'2-4,6' → [2, 3, 4, 6]"""
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def pick_pages(pages: list[dict], page_nos: list[int] | None) -> tuple[list[dict], str]:
    """page_nos 쪽만 고른다 (부분 시험용). 돌려주는 값: (쪽 목록, 모델에게 주는 안내). 안 고르면 전체 쪽."""
    if not page_nos:
        return pages, "아래는 문서 전체 쪽이다."
    missing = sorted(set(page_nos) - {p["page"] for p in pages})
    if missing:
        raise ValueError(f"문서에 없는 쪽: {missing}")
    picked = [p for p in pages if p["page"] in set(page_nos)]
    return picked, f"아래는 문서의 {', '.join(str(p['page']) for p in picked)}쪽이다 (일부 쪽만 넣었다)."


def used_lines(responses: dict[str, dict]) -> str:
    """⑤(서술형)에 넘길 글: ①~④가 근거로 쓴 원문 줄. ⑤는 다른 묶음 칸을 못 봐
    같은 줄을 미정의 항목에 다시 넣었다(실버 20건 미정의 항목 97개 중 41개). 서술은 막지 않는다:
    TO21 예제 25는 정식 칸과 같은 줄도 서술에 둔다(S14_SPECIAL의 EmS, waste와 S15_WASTE). 같은 MSDS의 같은 줄은 한 번만 적는다."""
    lines, seen = [], set()
    for bid, resp in responses.items():
        if bid == "b5":
            continue
        for e in (resp or {}).get("evidence") or []:
            text, idx = (e.get("source_text") or "").strip(), e.get("msds_index", 0)
            if not text or (idx, text) in seen:
                continue
            seen.add((idx, text))
            lines.append(f"- [MSDS {idx}, {e.get('page')}쪽, {e.get('field')}] {text}")
    return "\n".join(lines)


def after_fallback(failed, res2, fb: str):
    """대체 모델로 다시 보낸 결과. 실패한 요청도 비용이 들었으므로 요청 기록·횟수·시간을 이어 붙인다.
    (예: medium 추론이 출력 한도 64,000을 다 쓰고 잘린 요청, 약 $0.29)"""
    res2.errors = failed.errors + [f"→ 대체 모델 {fb} 사용"] + res2.errors
    res2.requests = failed.requests + res2.requests
    res2.attempts += failed.attempts
    res2.seconds += failed.seconds
    return res2


_NEG = re.compile(r"해당\s*(사항\s*)?없|해당(되|하)지\s*않|[비미]해당|등재되지\s*않|not\s+(listed|applicable|regulated)"
                  r"|\bN/?A\b", re.I)
_POS = re.compile(r"(?<![비미])해당(?!\s*(사항\s*)?없|되지|하지)|(?<!not )\blisted\b", re.I)
_REG_FIELD = re.compile(r"(?:msds\[\d+\]\.)?regulations\[(\d+)\]")   # 모델이 앞에 msds[i].를 붙이기도 한다


def applicable_conflicts(doc: dict) -> list[dict]:
    """15항 규제 행 중 근거 원문은 '해당없음' 꼴인데 applicable이 '해당'인 행. 고치지 않고 알리기만 한다.

    한 근거에 해당·해당없음이 같이 있으면 기계가 가리지 않는다(사람 검수 몫).
    """
    out = []
    for mi, m in enumerate(doc.get("msds") or []):
        texts: dict[int, list[str]] = {}
        for e in m.get("evidence") or []:
            if (k := _REG_FIELD.match(e.get("field") or "")) and (t := (e.get("source_text") or "").strip()):
                texts.setdefault(int(k.group(1)), []).append(t)
        for k, r in enumerate(m.get("regulations") or []):
            src = " | ".join(texts.get(k, []))
            if r.get("applicable") == "해당" and _NEG.search(src) and not _POS.search(src):
                out.append({"msds": mi, "row": k, "applicable": "해당", "source_text": src})
    return out


def find_reuse_run(runs: list[Path], doc_id: str) -> Path:
    """이전 실행 여러 개 중 이 문서의 응답(묶음 ①)이 있는 실행 하나."""
    hits = [r for r in runs if (r / "raw" / f"{doc_id}_b1.json").exists()]
    if not hits:
        raise RuntimeError(f"{doc_id}: 다시 쓸 이전 응답이 없습니다 ({', '.join(map(str, runs))})")
    if len(hits) > 1:
        raise RuntimeError(f"{doc_id}: 이전 응답이 둘 이상의 실행에 있습니다 ({', '.join(map(str, hits))})")
    return hits[0]


def reused_response(run: Path, doc_id: str, bid: str) -> dict:
    """이전 실행에서 받은 묶음 응답. 실패했거나 없으면 멈춘다(칸이 조용히 빠지지 않게)."""
    p = run / "raw" / f"{doc_id}_{bid}.json"
    parsed = json.loads(p.read_text(encoding="utf-8")).get("parsed") if p.exists() else None
    if parsed is None:
        raise RuntimeError(f"{doc_id}: {run.name}의 묶음 {bid} 응답이 없어 다시 쓸 수 없습니다")
    return parsed


def silver_tag(model_tag: str) -> str:
    """실버를 저장할 자리(data/silver/<자리>). 검수표·골드 도구는 gpt·claude 두 자리만 읽는다.
    models.yaml의 silver_slot이 있으면 그 자리(예: gpt54mini → gpt), 없으면 태그 이름. 실제 모델은 doc.extraction.engine에 남는다."""
    return load_model_config(model_tag).get("silver_slot") or model_tag


def save_run_config(run: Path, model_tag: str, mode: str, input_mode: str | None = None,
                    page_nos: list[int] | None = None) -> None:
    """같은 설정으로 다시 돌릴 수 있도록 실행 당시 설정을 복사해 둔다. input_mode가 없으면 manifest 값을, page_nos가 없으면 전체 쪽을 썼다."""
    run.mkdir(parents=True, exist_ok=True)
    shutil.copy(paths.CONFIGS / "models.yaml", run / "models.yaml")
    shutil.copy(paths.CONFIGS / "bundles.yaml", run / "bundles.yaml")
    info = {"model_tag": model_tag, "mode": mode, "prompt_version": PROMPT_VERSION,
            "preprocess_version": PREPROCESS_VERSION, "input_mode": input_mode or "manifest",
            "pages": page_nos or "전체"}
    (run / "run_info.yaml").write_text(yaml.safe_dump(info, allow_unicode=True), encoding="utf-8")


def extract_document(doc_id: str, model_tag: str, mode: str, run_name: str,
                     bundle_ids: list[str] | None = None, input_mode: str | None = None,
                     page_nos: list[int] | None = None, reuse_run: Path | None = None) -> dict:
    """reuse_run이 있으면 bundle_ids만 새로 부르고 나머지 묶음은 그 실행의 응답을 그대로 쓴다(묶음 일부 다시 뽑기)."""
    assert mode in ("silver", "baseline")
    assert reuse_run is None or bundle_ids, "다시 뽑을 묶음(bundle_ids)을 정해야 합니다"
    run = paths.run_dir(run_name)
    row = manifest.get(doc_id)
    cfg = load_model_config(model_tag)
    client = ChatClient(cfg)
    bundles = load_bundles()
    order = list(bundles.keys()) if reuse_run else (bundle_ids or list(bundles.keys()))
    if "b1" not in order:
        order = ["b1"] + order       # 성분 목록이 필요하므로 b1은 항상 먼저

    pages = load_pages(doc_id)
    got = pages["meta"].get("preprocess_version")
    if got != PREPROCESS_VERSION:   # 실행 기록의 전처리 버전과 실제 입력이 어긋나지 않게 한다
        raise RuntimeError(f"{doc_id}: 전처리 버전 {got} ≠ {PREPROCESS_VERSION}. "
                           f"python scripts/preprocess.py --docs {doc_id} --force 로 다시 만드세요")
    input_mode = input_mode or row.get("input_mode") or pages["meta"]["input_mode"]   # 인자는 입력 비교 실험용
    picked, pages_note = pick_pages(pages["pages"], page_nos)
    parts = page_parts(picked, input_mode, cfg.get("image_detail", "high"))

    responses: dict[str, dict] = {}
    comp_text = ""
    reused: list[str] = []
    for bid in order:
        b = bundles[bid]
        if reuse_run and bid not in bundle_ids:
            responses[bid] = reused_response(reuse_run, doc_id, bid)
            reused.append(bid)
            if bid == "b1":
                comp_text = components_summary(responses[bid])
            continue
        system, bundle_prompt = load_prompt(bid, mode)
        schema = bundle_response_schema(b.keys, b.doc_keys, with_review=(mode == "silver"))
        intro = bundle_prompt
        if bid != "b1":
            intro += "\n\n## [성분 목록] 묶음 ①에서 뽑은 성분. comp_ref·refs는 이 번호를 쓴다\n" + comp_text
        if bid == "b5" and (used := used_lines(responses)):
            intro += ("\n\n## [이미 정식 칸에 들어간 원문 줄] 묶음 ①~④가 근거로 쓴 줄. "
                      "extras에 다시 넣지 않는다\n" + used)
        user = [{"type": "text", "text": intro + "\n\n" + pages_note}] + parts

        res = client.call(system, user, schema, schema_name=f"msds_{bid}")
        # 대체 모델(fallback_models)로 한 번 더
        if not res.ok:
            for fb in cfg.get("fallback_models") or []:
                res2 = ChatClient(cfg, model=fb).call(system, user, schema, schema_name=f"msds_{bid}")
                ok2 = res2.ok      # 이어 붙이면 앞선 오류가 errors에 남아 ok가 항상 거짓이 된다
                res = after_fallback(res, res2, fb)
                if ok2:
                    break

        _write_json(run / "raw" / f"{doc_id}_{bid}.json", {
            "doc_id": doc_id, "bundle": bid, "model": res.model, "mode": res.mode,
            "finish_reason": res.finish_reason, "usage": res.usage, "seconds": round(res.seconds, 1),
            "request_usage": [r["usage"] for r in res.requests],   # 다시 보낸 요청도 비용이 든다. usage는 마지막 요청뿐
            "attempts": res.attempts, "errors": res.errors, "parsed": res.parsed, "raw_text": res.raw_text,
        })
        _log(run, {"doc_id": doc_id, "bundle": bid, "model": res.model, "structured": res.mode,
                   "finish_reason": res.finish_reason, "ok": res.ok, "attempts": res.attempts,
                   "usage": res.usage, "request_usage": [r["usage"] for r in res.requests],
                   "seconds": round(res.seconds, 1), "errors": res.errors[:3],
                   "prompt_version": PROMPT_VERSION, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        if res.parsed is not None:
            responses[bid] = res.parsed
            if bid == "b1":
                comp_text = components_summary(res.parsed)
        elif bid == "b1":
            raise RuntimeError(f"{doc_id}: 묶음 ① 실패로 중단합니다. {run / 'raw' / f'{doc_id}_b1.json'} 확인")

    engine = f"{client.model} ({mode}, prompt {PROMPT_VERSION})"
    if reused:   # 어느 묶음을 어느 실행에서 가져왔는지 결과에 남긴다
        engine = (f"{client.model} ({mode}, prompt {PROMPT_VERSION}: {'·'.join(b for b in order if b not in reused)}; "
                  f"{'·'.join(reused)}는 {reuse_run.name} 응답)")
    doc, review_items, warnings = merge_bundles(
        responses, row, engine=engine,
        evidence_method=cfg.get("evidence_method", "vLM"))
    schema_errors = validate_to21(doc)
    v_results = run_to21_validator(doc)
    conflicts = applicable_conflicts(doc)
    _write_json(run / "validation" / f"{doc_id}.json", {
        "merge_warnings": warnings,
        "input_sources": {p["page"]: p["source"] for p in pages["pages"] if p["state"] == "정상"},   # 쪽마다 모델이 읽은 글
        "missing_bundles": [b for b in order if b not in responses],
        "schema_errors": schema_errors,
        "to21_validator": v_results,
        "reused_bundles": {b: reuse_run.name for b in reused},
        "applicable_conflicts": conflicts,   # 1행이라도 있으면 확인 필요
    })
    _write_json(run / "outputs" / f"{doc_id}.json", doc)
    if mode == "silver":
        _write_json(paths.silver_path(silver_tag(model_tag), doc_id), doc)
        _write_json(paths.silver_review_path(silver_tag(model_tag), doc_id), review_items)
    return {
        "doc_id": doc_id,
        "missing_bundles": [b for b in order if b not in responses],
        "schema_errors": len(schema_errors),
        "validator_errors": sum(1 for r in v_results if r["level"] == "오류"),
        "applicable_conflicts": len(conflicts),
        "check_needed": bool(conflicts),
        "warnings": warnings,
    }
