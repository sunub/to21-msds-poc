"""문서 하나를 처음부터 끝까지 처리하는 항목별 실행기 (B, ADR-001·003·006).

입력 읽기 → 항목별 동시 호출 → 줄 번호 검사, 실패·문제 항만 1회 재추출 → 펼치기 → 검사 → 기록.
한 항의 호출이 실패해도 그 항만 실패로 남기고 나머지는 계속한다.

runs/<실행 이름>/ 에 남는 것
  outputs/<문서>.json            TO21 v0.6 문서
  checks/<문서>.json             항별 결과, 스키마·TO21 검증기 결과, 펼치기 문제, 경고, 사람 검토할 항
  raw/<문서>_m<i>_s<NN>.json     항별 모델 응답과 사용량, 요청별 기록 requests (재추출했으면 다른 시도도)
  timing.jsonl                   단계별 시간: inputs, call, reextract, expand, checks, total
  run_info.yaml                  모델, 프롬프트 버전·해시, 스키마 버전, 시각, git 커밋 (save_run_info)
시스템 안내문과 중간 형식 스키마는 명세서 내용이라 저장하지 않는다 (D-47).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yaml

from msds.checks.validator import run_to21_validator
from msds.common import manifest
from msds.common.merge import SCHEMA_VERSION, now_kst
from msds.common.paths import DATA, PAGES, ROOT, RUNS
from msds.common.schema import validate_to21
from msds.extract.client import ChatClient, load_model_config
from msds.extract.expand import to_to21
from msds.extract.inputs import SECTION_NOS, DocumentInput, load_document, section_lines
from msds.extract.section_prompts import SECTION_PROMPT_VERSION, build_system, build_user, prompt_hash
from msds.extract.section_specs import response_schema

DOC_TIME_LIMIT = 300          # 초. 넘으면 경고만 남기고 멈추지 않는다
_LINE_KEYS = ("line", "start", "end")
_FEEDBACK_MAX = 20            # 다시 보낼 때 적는 문제 수


@dataclass
class SectionResult:
    msds_index: int
    section_no: int
    parsed: dict | None       # 쓰기로 한 시도의 응답
    ok: bool
    errors: list[str]
    seconds: float            # 이 항에 쓴 시간 (재추출 포함)
    usage: dict               # 이 항에 쓴 토큰 (재추출 포함)
    attempts: int
    reextracted: bool         # 재추출 결과를 썼는가


def check_section(parsed: dict | None, allowed_ids: set[str]) -> list[str]:
    """응답 안의 모든 line, lines 값, start, end가 allowed_ids 안에 있는지. 문제 문장 목록."""
    problems: list[str] = []

    def check(path: str, value) -> None:
        if value is not None and not (isinstance(value, str) and value in allowed_ids):
            problems.append(f"{path}: 원문에 없는 줄 번호 {value}")

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}" if path else k
                if k in _LINE_KEYS:
                    check(p, v)
                elif k == "lines" and isinstance(v, dict):
                    for field, lid in v.items():
                        check(f"{p}.{field}", lid)
                else:
                    walk(v, p)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(parsed, "")
    return problems


# ── 항 하나 ────────────────────────────────────────────

def _attempt(client, system: str, user: list[dict], schema: dict, schema_name: str, allowed: set[str]) -> dict:
    """호출 한 번. 예외도 실패한 시도로 돌려준다.
    서버 스키마의 필수 칸을 TO21 필수 칸과 line·lines로 줄여, 모델이 값 없는 칸을 쓰지 않게 한다 (ADR-017)."""
    t0 = time.perf_counter()
    try:
        r = client.call(system, user, schema, schema_name, require_all=False)
        rec = {"ok": r.ok, "parsed": r.parsed, "raw_text": r.raw_text, "mode": r.mode,
               "finish_reason": r.finish_reason, "usage": r.usage or {}, "attempts": r.attempts,
               "errors": list(r.errors), "requests": list(r.requests)}
    except Exception as e:
        rec = {"ok": False, "parsed": None, "raw_text": None, "mode": None, "finish_reason": None,
               "usage": {}, "attempts": 1, "errors": [f"호출 예외: {type(e).__name__}: {str(e)[:300]}"],
               "requests": []}
    rec["seconds"] = round(time.perf_counter() - t0, 3)
    rec["check_problems"] = check_section(rec["parsed"], allowed)
    return rec


def _sum_usage(*usages: dict) -> dict:
    out: dict = {}
    for u in usages:
        for k, v in (u or {}).items():
            if v is not None:
                out[k] = out.get(k, 0) + v
    return out


def _run_section(client, doc: DocumentInput, msds_index: int, no: int, system: str, schema: dict,
                 allowed: set[str]) -> tuple[SectionResult, dict, dict | None]:
    """반환: (항 결과, 첫 시도, 재추출 시도 또는 None)."""
    lines = section_lines(doc, msds_index, no)
    name = f"sec{no:02d}"
    first = _attempt(client, system, build_user(no, lines), schema, name, allowed)
    second = None
    if not first["ok"] or first["check_problems"]:
        feedback = "\n".join(f"- {x}" for x in (first["errors"] + first["check_problems"])[:_FEEDBACK_MAX])
        second = _attempt(client, system, build_user(no, lines, feedback), schema, name, allowed)
    better = (second is not None and second["ok"]
              and (not first["ok"] or len(second["check_problems"]) < len(first["check_problems"])))
    chosen = second if better else first
    tried = [first] + ([second] if second else [])
    result = SectionResult(msds_index, no, chosen["parsed"], chosen["ok"], chosen["errors"],
                           round(sum(a["seconds"] for a in tried), 3), _sum_usage(*(a["usage"] for a in tried)),
                           sum(a["attempts"] for a in tried), better)
    return result, first, second


# ── 문서 하나 ──────────────────────────────────────────

def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def run_document(doc_id: str, model_tag: str, run_name: str, client=None, *,
                 max_workers: int | None = None, pages_dir=PAGES, sections_dir=DATA / "sections",
                 codes_dir=DATA / "codes", runs_dir=RUNS) -> dict:
    """요약 dict를 돌려준다: doc_id, seconds, sections_ok, sections_failed, reextracted, schema_errors, warnings."""
    t_start = time.perf_counter()
    cfg = load_model_config(model_tag)
    client = client or ChatClient(cfg)
    row = manifest.get(doc_id)
    run = Path(runs_dir) / run_name
    timing: list[dict] = []

    def stage(name: str, seconds: float, msds_index=None, section=None, usage: dict | None = None) -> None:
        u = usage or {}
        timing.append({"doc_id": doc_id, "stage": name, "msds_index": msds_index, "section": section,
                       "seconds": round(seconds, 3), "prompt_tokens": u.get("prompt_tokens"),
                       "completion_tokens": u.get("completion_tokens")})

    # 1. 입력
    t = time.perf_counter()
    doc = load_document(doc_id, pages_dir, sections_dir, codes_dir)
    stage("inputs", time.perf_counter() - t)

    # 2~3. 항목별 동시 호출과 1회 재추출. 안내문은 워크북을 읽으므로 스레드에 넘기기 전에 만든다.
    prompts = {no: (build_system(no), response_schema(no)) for no in SECTION_NOS}
    futures = {}
    with ThreadPoolExecutor(max_workers=max_workers or cfg.get("concurrency") or 16) as pool:
        for part in doc.msds:
            first_page, last_page = part.pages
            allowed = {l.id for l in doc.lines if first_page <= l.page <= last_page}
            for no in SECTION_NOS:
                futures[(part.index, no)] = pool.submit(_run_section, client, doc, part.index, no,
                                                        *prompts[no], allowed)
    outcomes = [futures[k].result() for k in sorted(futures)]

    results: list[SectionResult] = []
    section_checks: list[dict] = []
    for res, first, second in outcomes:
        results.append(res)
        chosen = second if res.reextracted else first
        stage("call", first["seconds"], res.msds_index, res.section_no, first["usage"])
        if second:
            stage("reextract", second["seconds"], res.msds_index, res.section_no, second["usage"])
        raw = {"doc_id": doc_id, "msds_index": res.msds_index, "section": res.section_no,
               "reextracted": res.reextracted, **chosen}
        if res.reextracted:
            raw["first_attempt"] = first
        elif second:
            raw["reextract_attempt"] = second
        _write_json(run / "raw" / f"{doc_id}_m{res.msds_index}_s{res.section_no:02d}.json", raw)
        section_checks.append({"msds_index": res.msds_index, "section": res.section_no, "ok": res.ok,
                               "errors": res.errors, "check_problems": chosen["check_problems"],
                               "reextracted": res.reextracted, "attempts": res.attempts,
                               "seconds": res.seconds, "usage": res.usage})

    # 4. 펼치기. 실패한 항은 None으로 넘겨 펼치기가 missing_section으로 남긴다.
    t = time.perf_counter()
    parts: list[dict[int, dict | None]] = [{} for _ in doc.msds]
    for res in results:
        parts[res.msds_index][res.section_no] = res.parsed if res.ok else None
    out, expand_problems = to_to21(row, parts, doc.lines, f"{model_tag}:{cfg['model']}")
    stage("expand", time.perf_counter() - t)

    # 5. 검사
    t = time.perf_counter()
    schema_errors = validate_to21(out)
    try:
        validator = run_to21_validator(out)
    except Exception as e:
        validator = [{"level": "예외", "rule": None, "field": None, "message": f"{type(e).__name__}: {e}"}]
    stage("checks", time.perf_counter() - t)

    total = time.perf_counter() - t_start
    warnings = list(doc.warnings)
    if total > DOC_TIME_LIMIT:
        warnings.append(f"5분 초과: {total:.0f}초")
    stage("total", total, usage=_sum_usage(*(r.usage for r in results)))

    review = {(r.msds_index, r.section_no) for r in results if not r.ok}
    review |= {(c["msds_index"], c["section"]) for c in section_checks if c["check_problems"]}
    review |= {(p["msds_index"], p["section"]) for p in expand_problems}

    # 6. 기록
    _write_json(run / "outputs" / f"{doc_id}.json", out)
    _write_json(run / "checks" / f"{doc_id}.json", {
        "sections": section_checks,
        "schema_errors": schema_errors,
        "to21_validator": validator,
        "expand_problems": expand_problems,
        "warnings": warnings,
        "needs_review": [{"msds_index": i, "section": no} for i, no in sorted(review)],
    })
    run.mkdir(parents=True, exist_ok=True)
    with open(run / "timing.jsonl", "a", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in timing)

    return {"doc_id": doc_id, "seconds": round(total, 1),
            "sections_ok": sum(r.ok for r in results), "sections_failed": sum(not r.ok for r in results),
            "reextracted": sum(r.reextracted for r in results), "schema_errors": len(schema_errors),
            "warnings": warnings}


# ── 실행 기록 ──────────────────────────────────────────

def _git_commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                           timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout.strip() or None) if r.returncode == 0 else None


def save_run_info(run: Path, model_tag: str, pages_dir=PAGES) -> None:
    """같은 조건으로 다시 돌릴 수 있게 모델·프롬프트·스키마 버전과 쪽 글자 폴더를 남긴다.
    주소·키·환경변수 값은 쓰지 않는다. 쪽 글자 폴더는 저장소 기준 상대 경로로 쓴다."""
    cfg = load_model_config(model_tag)
    info = {
        "model_tag": model_tag,
        "model": cfg["model"],
        "prompt_version": SECTION_PROMPT_VERSION,
        "prompt_hashes": {no: prompt_hash(no) for no in SECTION_NOS},
        "schema_version": SCHEMA_VERSION,
        "pages_dir": os.path.relpath(pages_dir, ROOT),
        "started_at": now_kst(),
        "git_commit": _git_commit(),
    }
    run = Path(run)
    run.mkdir(parents=True, exist_ok=True)
    (run / "run_info.yaml").write_text(yaml.safe_dump(info, allow_unicode=True, sort_keys=False), encoding="utf-8")
