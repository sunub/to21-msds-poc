"""문서 하나를 처음부터 끝까지 처리하는 항목별 실행기 (B, ADR-001·003·006).

입력 읽기 → 항목별 동시 호출 → 줄 번호 검사, 실패·문제 항만 1회 재추출 → 펼치기 → 검사 → 기록.
한 항의 호출이 실패해도 그 항만 실패로 남기고 나머지는 계속한다.
다만 모델 서버가 연달아 응답하지 않으면 항들이 함께 쓰는 ChatClient의 관문(ServerGate)이 닫혀,
남은 항과 재추출은 요청을 보내지 않고 바로 실패로 남는다 (client.ServerUnreachable).
모델 설정의 rows_sections에 든 항은 행 형식으로 받는다: call_text → rows.parse_rows → 스키마 검증.
버린 줄의 오류도 재추출 피드백에 넣는다 (ADR-019).
모델 설정의 image_input이 참이면 2항 호출에 2항이 있는 쪽 이미지를 붙인다. 펼친 뒤 H코드로 추론한 그림문자와
모델이 읽은 그림문자를 대조해 checks에 남긴다. 대조 결과로 재추출하지 않고 다르면 사람 검토로 표시한다 (ADR-019).

runs/<실행 이름>/ 에 남는 것
  outputs/<문서>.json            TO21 v0.6 문서
  checks/<문서>.json             항별 결과(받은 방식 mode 포함), 스키마·TO21 검증기 결과, 펼치기 문제, 경고, 항목 분할 방식,
                                 그림문자 대조(pictogram_check), 사람 검토할 항
  raw/<문서>_m<i>_s<NN>.json     항별 모델 응답과 사용량, 요청별 기록 requests (재추출했으면 다른 시도도).
                                 그 항이 끝나는 즉시 쓴다 (서버가 꺼져도 끝난 항의 값이 남고, API가 추출 중에 읽는다)
  timing.jsonl                   단계별 시간: inputs, call, reextract, expand, checks, total
  run_info.yaml                  모델, 프롬프트 버전·해시, 스키마 버전, 시각, git 커밋 (save_run_info)
시스템 안내문과 중간 형식 스키마는 명세서 내용이라 저장하지 않는다 (D-47).

진행 알림 (on_event, 서비스 API가 쓴다). 호출 스레드에서도 불리므로 받는 쪽이 잠금을 건다.
  {"type": "plan", "msds_count", "page_count", "sections": [{msds_index, section, title, pages}]}  입력을 읽은 직후 한 번
  {"type": "section_started", "msds_index", "section"}                                          항 호출을 시작할 때
  {"type": "section_done", "msds_index", "section", "ok", "reextracted", "needs_review", "seconds", "errors"}
  {"type": "finalize"}                                                                          모든 항이 끝나고 펼치기 전
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yaml

from msds.checks.validator import run_to21_validator
from msds.common import manifest
from msds.common.merge import SCHEMA_VERSION, now_kst
from msds.common.paths import DATA, PAGES, ROOT, RUNS
from msds.common.schema import validate, validate_to21
from msds.extract.client import ChatClient, load_model_config
from msds.extract.expand import to_to21
from msds.extract.inputs import _PAGE_FILE, EXTRACT_SECTIONS, SECTION_NOS, DocumentInput, load_document, model_lines, section_lines
from msds.extract.pictogram_check import check_msds, load_hazard_map
from msds.extract.rows import parse_rows
from msds.extract.section_prompts import SECTION_PROMPT_VERSION, build_system, build_user, prompt_hash
from msds.extract.section_specs import load_specs, response_schema

DOC_TIME_LIMIT = 300          # 초. 넘으면 경고만 남기고 멈추지 않는다
_LINE_KEYS = ("line", "start", "end")
_FEEDBACK_MAX = 20            # 다시 보낼 때 적는 문제 수
# 모델을 부르지 않는 항: 추출 대상(inputs.EXTRACT_SECTIONS) 밖의 항. 펼치기에는 빈 응답으로 넘긴다.
SKIPPED_SECTIONS = tuple(no for no in SECTION_NOS if no not in EXTRACT_SECTIONS)
# 명세서 1_항목정의에서 type이 code인 행 칸. 한 행만 빈 것은 '급성 독성 자료 없음'처럼 묶어 적은 행일 수 있어
# 표 전체가 빈 경우만 본다. 규제 법령은 항목 코드에서 채운다(expand.fill_law).
# CMR 기관은 '발암성 : 자료없음'처럼 기관 없는 행이 있어, 모두 자료없음인 문서는 표 전체가 빌 수 있으므로 보지 않는다.
_CODE_COLUMNS = {"physchem": "prop_code", "toxicity": "endpoint", "ecotox": "endpoint", "regulations": "item_code"}
IMAGE_SECTION = 2             # 쪽 이미지를 붙이는 항 (그림문자, ADR-019)
IMAGE_PAGES = 2               # 붙이는 쪽 이미지 수 상한
OUTSIDE_MANIFEST_WARNING = "manifest에 없는 문서: 쪽 글자 폴더의 meta.json을 씀"


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


def check_section(parsed: dict | None, allowed_ids: set[str], no: int | None = None) -> list[str]:
    """응답 안의 모든 line, lines 값, start, end가 allowed_ids 안에 있는지, 코드표 칸이 통째로 비지 않았는지.
    문제 문장 목록. 2항(no=2)은 H코드가 있는데 유해성 분류(hazard.classes)가 비면 문제로 잡는다.
    classified가 거짓이면 잡지 않는다 (ADR-024)."""
    problems: list[str] = []
    hazard = parsed.get("hazard") if no == 2 and isinstance(parsed, dict) else None
    if isinstance(hazard, dict) and hazard.get("classified") is not False:
        h = hazard.get("h_statements")
        if isinstance(h, list) and h and not hazard.get("classes"):
            problems.append(f"hazard.classes가 비었음: 원문의 유해성 분류 행(예: 인화성 액체 구분 2)을 "
                            f"hazard.classes에 한 행씩 쓴다 (H코드 {len(h)}개가 있음)")
    for table, column in _CODE_COLUMNS.items():
        rows = (parsed or {}).get(table) or []
        if len(rows) >= 2 and all(r.get(column) is None for r in rows):
            problems.append(f"{table}: 모든 행의 {column}가 비었음. "
                            "[코드표]에 맞는 코드를 쓰고, 맞는 코드가 없는 값은 extras에 쓴다")

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

def _attempt(client, no: int, system: str, user: list[dict], schema: dict, allowed: set[str],
             rows: bool = False, rows_max_tokens: int | None = None) -> dict:
    """호출 한 번. 예외도 실패한 시도로 돌려준다.
    JSON 경로는 서버 스키마의 필수 칸을 TO21 필수 칸과 line·lines로 줄여, 모델이 값 없는 칸을 쓰지 않게 한다 (ADR-017).
    rows면 글로 받아 parse_rows로 바꾸고 schema로 검증한다. 버린 줄과 검증 문제는 errors에 담는다.
    출력 한도는 rows_max_tokens다. None이면 call_text가 설정의 max_tokens를 쓴다 (ADR-021).
    표 하나라도 읽혀 검증을 통과하면 ok다. 버린 줄이 있어도 남은 행은 쓴다 (ADR-019)."""
    t0 = time.perf_counter()
    try:
        if rows:
            r = client.call_text(system, user, max_tokens=rows_max_tokens)
            parsed, errors = parse_rows(r.raw_text, no)
            schema_errors = validate(parsed, schema) if parsed else []
            errors += [f"검증 실패: {e}" for e in schema_errors]
            parsed, ok = parsed or None, bool(parsed) and not schema_errors
        else:
            r = client.call(system, user, schema, f"sec{no:02d}", require_all=False)
            parsed, ok, errors = r.parsed, r.ok, []
        rec = {"ok": ok, "parsed": parsed, "raw_text": r.raw_text, "mode": r.mode,
               "finish_reason": r.finish_reason, "usage": r.usage or {}, "attempts": r.attempts,
               "errors": list(r.errors) + errors, "requests": list(r.requests)}
    except Exception as e:
        rec = {"ok": False, "parsed": None, "raw_text": None, "mode": None, "finish_reason": None,
               "usage": {}, "attempts": 1, "errors": [f"호출 예외: {type(e).__name__}: {str(e)[:300]}"],
               "requests": []}
    rec["seconds"] = round(time.perf_counter() - t0, 3)
    rec["check_problems"] = check_section(rec["parsed"], allowed, no)
    return rec


def _sum_usage(*usages: dict) -> dict:
    out: dict = {}
    for u in usages:
        for k, v in (u or {}).items():
            if v is not None:
                out[k] = out.get(k, 0) + v
    return out


def _problems(attempt: dict) -> list[str]:
    """다시 보낼 때 적을 문제: 호출·검증 오류(행 형식이면 버린 줄 포함)와 줄 번호 검사 문제.
    JSON 경로는 ok이면 errors가 비어 있어, 지금까지처럼 줄 번호 검사 문제만 남는다."""
    return attempt["errors"] + attempt["check_problems"]


def section_images(doc: DocumentInput, msds_index: int, pages_dir: Path) -> tuple[list[Path], list[str]]:
    """2항 구간 줄이 있는 쪽의 이미지 pages_dir/<문서>/pNNN.png를 쪽 순서대로 최대 IMAGE_PAGES장. 문서 머리의 쪽은 세지 않는다.
    반환: (있는 파일, 없는 파일의 경고)."""
    span = section_lines(doc, msds_index, IMAGE_SECTION, with_preamble=False)
    pages = list(dict.fromkeys(l.page for l in span))[:IMAGE_PAGES]
    found, warnings = [], []
    for page in pages:
        path = Path(pages_dir) / doc.doc_id / f"p{page:03d}.png"
        if path.is_file():
            found.append(path)
        else:
            warnings.append(f"{IMAGE_SECTION}항 쪽 이미지 없음: {path.name}, 글만 보냄 (MSDS {msds_index})")
    return found, warnings


def _run_section(client, doc: DocumentInput, msds_index: int, no: int, system: str, schema: dict,
                 allowed: set[str], rows: bool = False, images: list[Path] = (),
                 rows_max_tokens: int | None = None) -> tuple[SectionResult, dict, dict | None]:
    """반환: (항 결과, 첫 시도, 재추출 시도 또는 None). images는 첫 시도와 재추출 모두에 붙인다."""
    lines = model_lines(doc, msds_index, no)      # 쪽 머리글·바닥글·쪽 번호는 보내지 않는다
    first = _attempt(client, no, system, build_user(no, lines, images=images), schema, allowed, rows,
                     rows_max_tokens)
    second = None
    if not first["ok"] or _problems(first):
        feedback = "\n".join(f"- {x}" for x in _problems(first)[:_FEEDBACK_MAX])
        second = _attempt(client, no, system, build_user(no, lines, feedback, images), schema, allowed, rows,
                          rows_max_tokens)
    better = (second is not None and second["ok"]
              and (not first["ok"] or len(_problems(second)) < len(_problems(first))))
    chosen = second if better else first
    tried = [first] + ([second] if second else [])
    result = SectionResult(msds_index, no, chosen["parsed"], chosen["ok"], chosen["errors"],
                           round(sum(a["seconds"] for a in tried), 3), _sum_usage(*(a["usage"] for a in tried)),
                           sum(a["attempts"] for a in tried), better)
    return result, first, second


# ── 문서 하나 ──────────────────────────────────────────

def _write_json(path: Path, obj) -> None:
    """임시 파일에 쓰고 이름을 바꾼다. API가 쓰는 도중의 파일을 읽지 않게 한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def raw_path(run: Path, doc_id: str, msds_index: int, section: int) -> Path:
    return Path(run) / "raw" / f"{doc_id}_m{msds_index}_s{section:02d}.json"


def _raw_record(doc_id: str, res: SectionResult, first: dict, second: dict | None) -> dict:
    chosen = second if res.reextracted else first
    raw = {"doc_id": doc_id, "msds_index": res.msds_index, "section": res.section_no,
           "reextracted": res.reextracted, **chosen}
    if res.reextracted:
        raw["first_attempt"] = first
    elif second:
        raw["reextract_attempt"] = second
    return raw


def doc_meta_from_pages(doc_id: str, pages_dir) -> dict | None:
    """manifest에 없는 문서의 문서 정보를 <pages_dir>/<doc_id>/meta.json에서 manifest 행과 같은 키로 만든다 (format40).
    쪽수(page_count)가 없으면 pNNN.txt 수를 쓴다. manifest 밖 문서는 평가용이 아닌 것으로 본다(purpose 기타).
    meta.json이 없으면 None."""
    doc_dir = Path(pages_dir) / doc_id
    path = doc_dir / "meta.json"
    if not path.is_file():
        return None
    meta = json.loads(path.read_text(encoding="utf-8"))
    pages = meta.get("page_count") or sum(1 for p in doc_dir.iterdir() if _PAGE_FILE.match(p.name))
    return {"doc_id": doc_id, "source_file": meta.get("source_file"), "pages": pages,
            "text_layer": meta.get("text_layer"), "language": None, "purpose": "기타"}


def section_plan(doc: DocumentInput) -> dict:
    """진행 알림의 plan: 건마다 추출 대상 항(EXTRACT_SECTIONS)과 그 항이 걸친 쪽(문서 머리 제외, fallback 항은 건의 쪽 전체)."""
    specs = load_specs()
    sections = [{"msds_index": part.index, "section": no, "title": specs[no].title,
                 "pages": sorted({l.page for l in section_lines(doc, part.index, no, with_preamble=False)})}
                for part in doc.msds for no in EXTRACT_SECTIONS]
    return {"type": "plan", "msds_count": len(doc.msds), "page_count": len({l.page for l in doc.lines}),
            "sections": sections}


def _section_done_event(res: SectionResult, first: dict, second: dict | None) -> dict:
    chosen = second if res.reextracted else first
    return {"type": "section_done", "msds_index": res.msds_index, "section": res.section_no, "ok": res.ok,
            "reextracted": res.reextracted, "needs_review": not res.ok or bool(_problems(chosen)),
            "seconds": res.seconds, "errors": list(res.errors)}


def run_document(doc_id: str, model_tag: str, run_name: str, client=None, *,
                 max_workers: int | None = None, pages_dir=PAGES, sections_dir=DATA / "sections",
                 codes_dir=DATA / "codes", runs_dir=RUNS,
                 on_event: Callable[[dict], None] | None = None) -> dict:
    """요약 dict를 돌려준다: doc_id, seconds, sections_ok, sections_failed, reextracted, schema_errors, warnings.
    manifest에 없는 문서는 쪽 글자 폴더의 meta.json으로 문서 정보를 만들고 경고를 남긴다. 그것도 없으면 KeyError.
    on_event가 있으면 진행을 알린다(모듈 설명의 진행 알림)."""
    emit = on_event or (lambda event: None)
    t_start = time.perf_counter()
    cfg = load_model_config(model_tag)
    client = client or ChatClient(cfg)
    meta_warnings: list[str] = []
    try:
        row = manifest.get(doc_id)
    except KeyError:
        row = doc_meta_from_pages(doc_id, pages_dir)
        if row is None:
            raise
        meta_warnings.append(OUTSIDE_MANIFEST_WARNING)
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
    emit(section_plan(doc))

    def run_one(msds_index: int, no: int, *args):
        emit({"type": "section_started", "msds_index": msds_index, "section": no})
        outcome = _run_section(client, doc, msds_index, no, *args)
        # 알리기 전에 쓴다: section_done을 본 화면이 바로 이 파일을 읽을 수 있어야 한다
        _write_json(raw_path(run, doc_id, msds_index, no), _raw_record(doc_id, *outcome))
        emit(_section_done_event(*outcome))
        return outcome

    # 2~3. 항목별 동시 호출과 1회 재추출. 안내문은 워크북을 읽으므로 스레드에 넘기기 전에 만든다.
    rows = set(cfg.get("rows_sections") or [])
    prompts = {no: (build_system(no, no in rows), response_schema(no)) for no in EXTRACT_SECTIONS}
    image_warnings: list[str] = []
    futures = {}
    with ThreadPoolExecutor(max_workers=workers(cfg, max_workers)) as pool:
        for part in doc.msds:
            images: list[Path] = []
            if cfg.get("image_input"):
                images, missing = section_images(doc, part.index, pages_dir)
                image_warnings += missing
            for no in EXTRACT_SECTIONS:
                # 줄 번호 검사는 그 항에 보낸 줄(문서 머리 + 항 구간, fallback 항은 건의 쪽 전체) 기준 (ADR-020)
                allowed = {l.id for l in section_lines(doc, part.index, no)}
                futures[(part.index, no)] = pool.submit(run_one, part.index, no,
                                                        *prompts[no], allowed, no in rows,
                                                        images if no == IMAGE_SECTION else [],
                                                        cfg.get("rows_max_tokens"))
    outcomes = [futures[k].result() for k in sorted(futures)]

    results: list[SectionResult] = []
    section_checks: list[dict] = []
    for res, first, second in outcomes:
        results.append(res)
        chosen = second if res.reextracted else first
        stage("call", first["seconds"], res.msds_index, res.section_no, first["usage"])
        if second:
            stage("reextract", second["seconds"], res.msds_index, res.section_no, second["usage"])
        section_checks.append({"msds_index": res.msds_index, "section": res.section_no, "ok": res.ok,
                               "mode": chosen["mode"], "errors": res.errors, "check_problems": chosen["check_problems"],
                               "reextracted": res.reextracted, "attempts": res.attempts,
                               "seconds": res.seconds, "usage": res.usage})

    # 4. 펼치기. 실패한 항은 None으로 넘겨 펼치기가 missing_section으로 남긴다.
    emit({"type": "finalize"})
    t = time.perf_counter()
    parts: list[dict[int, dict | None]] = [{no: {} for no in SKIPPED_SECTIONS} for _ in doc.msds]
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
    hazard_map = load_hazard_map()
    pictogram_check = [{"msds_index": i, **check_msds(m, hazard_map)} for i, m in enumerate(out["msds"])]
    stage("checks", time.perf_counter() - t)

    total = time.perf_counter() - t_start
    warnings = meta_warnings + list(doc.warnings) + image_warnings
    if total > DOC_TIME_LIMIT:
        warnings.append(f"5분 초과: {total:.0f}초")
    stage("total", total, usage=_sum_usage(*(r.usage for r in results)))

    review = {(r.msds_index, r.section_no) for r in results if not r.ok}
    review |= {(c["msds_index"], c["section"]) for c in section_checks if c["check_problems"] or c["errors"]}
    review |= {(p["msds_index"], p["section"]) for p in expand_problems}
    review |= {(p["msds_index"], IMAGE_SECTION) for p in pictogram_check if p.get("ok") is False}

    # 6. 기록
    _write_json(run / "outputs" / f"{doc_id}.json", out)
    _write_json(run / "checks" / f"{doc_id}.json", {
        "sections": section_checks,
        "schema_errors": schema_errors,
        "to21_validator": validator,
        "expand_problems": expand_problems,
        "warnings": warnings,
        "sections_method": doc.sections_method,
        "pictogram_check": pictogram_check,
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


def workers(cfg: dict, max_workers: int | None = None) -> int:
    """항목별 동시 호출 수: max_workers or cfg["concurrency"] or 16. run_document와 save_run_info가 함께 쓴다."""
    return max_workers or cfg.get("concurrency") or 16


def save_run_info(run: Path, model_tag: str, pages_dir=PAGES, max_workers: int | None = None) -> None:
    """같은 조건으로 다시 돌릴 수 있게 모델·프롬프트·스키마 버전과 쪽 글자 폴더를 남긴다.
    주소·키·환경변수 값은 쓰지 않는다. 쪽 글자 폴더는 저장소 기준 상대 경로로 쓴다."""
    cfg = load_model_config(model_tag)
    rows = set(cfg.get("rows_sections") or [])
    info = {
        "model_tag": model_tag,
        "model": cfg["model"],
        "prompt_version": SECTION_PROMPT_VERSION,
        "rows_sections": sorted(rows),
        "skipped_sections": list(SKIPPED_SECTIONS),          # 부르지 않는 항 (추출 목표 밖)
        "rows_max_tokens": cfg.get("rows_max_tokens"),      # 행 형식 호출의 출력 한도. 없으면 max_tokens (ADR-021)
        "image_input": bool(cfg.get("image_input")),
        "prompt_hashes": {no: prompt_hash(no, no in rows) for no in EXTRACT_SECTIONS},   # 실제로 보내는 안내문의 해시
        "schema_version": SCHEMA_VERSION,
        "pages_dir": os.path.relpath(pages_dir, ROOT),
        "concurrency": workers(cfg, max_workers),
        "started_at": now_kst(),
        "git_commit": _git_commit(),
    }
    run = Path(run)
    run.mkdir(parents=True, exist_ok=True)
    (run / "run_info.yaml").write_text(yaml.safe_dump(info, allow_unicode=True, sort_keys=False), encoding="utf-8")
