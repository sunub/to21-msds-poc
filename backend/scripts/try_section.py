"""항 하나·여러 개·문서 전체를 모델에 보내고 과정을 단계별로 보여 준다 (역할 B, 개발 전용, ADR-025).

사용법
  python scripts/try_section.py --model qwen36_35b_runpod --doc T21-S003 --section 11 --pages-dir ../data/pages/version9
  python scripts/try_section.py --model qwen36_35b_runpod --doc T21-S003 --section 11 --section 15 --pages-dir ../data/pages/version9
  python scripts/try_section.py --model qwen36_35b_runpod --doc T21-S003 --all --pages-dir ../data/pages/version9
  옵션: --dry-run  --system-file <경로>  --base-run <실행 이름>  --gold-dir <폴더>  --out-dir <폴더>  --json  --show-prompt

① 보낸 입력 ② 안내문 ③ 모델 원문 답 ④ 읽은 결과 ⑤ 펼친 TO21 칸 ⑥ 점수 전 → 후 순서로 찍는다. --dry-run은 ①②까지만 하고
서버를 부르지 않는다. 항 시험은 실행기의 _run_section을 그대로 부르고(재추출 포함), 기준 실행(--base-run, 없으면 같은 모델의
가장 최근 dev10 실행)의 다른 항 응답에 끼워 다시 펼쳐 채점한다. --all은 run_document를 그대로 부른다.
- 평가용 문서는 받지 않는다. 우회 옵션도 없다 (D-43).
- 안내문 글은 화면에만 찍고 파일에 쓰지 않는다. 기록에는 해시만 남긴다 (D-47).
- 기록: runs/manual/<시각>_<문서>_s<항들>/ 에 plan.json, raw/, result.json, run_info.yaml, timing.jsonl, outputs/<문서>.json
"""
import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

import _common  # noqa: F401  src 경로 등록
from msds.common import manifest
from msds.common.paths import DATA, PAGES, ROOT, RUNS, SILVER
from msds.evaluate.score import score_pair
from msds.extract import section_runner as sr
from msds.extract.client import ChatClient, load_model_config
from msds.extract.expand import to_to21
from msds.extract.inputs import SECTION_NOS, load_document, section_lines
from msds.extract.rows import row_tables
from msds.extract.section_prompts import SECTION_PROMPT_VERSION, build_system
from msds.extract.section_specs import META_REVISION_FIELDS, load_specs, response_schema

SECTIONS_DIR = DATA / "sections"
CODES_DIR = DATA / "codes"
ANSWER_LINES = 60          # ③에 찍는 모델 답의 줄 수


def _hash(text: str) -> str:
    """section_prompts.prompt_hash와 같은 규칙(sha256 앞 12자리). 바꾼 안내문에도 쓴다."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _rel(path) -> str:
    return os.path.relpath(Path(path).resolve(), ROOT)


# ── 서버 없이 ──────────────────────────────────────────

def plan(doc_id: str, model_tag: str, sections: list[int], pages_dir: Path, *,
         sections_dir: Path | None = None, codes_dir: Path | None = None) -> dict:
    """항마다 보낼 입력과 안내문. 평가용 문서면 ValueError (D-43). MSDS가 여러 건이면 첫 건만 본다.
    lines는 보내는 줄 수(문서 머리 포함), first·last·pages는 항 구간(머리 제외)이다."""
    if manifest.get(doc_id)["purpose"] == "평가":
        raise ValueError(f"{doc_id}는 평가용 문서라 수동 시험에 쓰지 않습니다 (D-43)")
    cfg = load_model_config(model_tag)
    doc = load_document(doc_id, Path(pages_dir), sections_dir or SECTIONS_DIR, codes_dir or CODES_DIR)
    rows = set(cfg.get("rows_sections") or [])
    warnings = list(doc.warnings)
    out = {}
    for no in sections:
        sent = section_lines(doc, 0, no)
        span = section_lines(doc, 0, no, with_preamble=False)
        images = []
        if cfg.get("image_input") and no == sr.IMAGE_SECTION:
            found, missing = sr.section_images(doc, 0, Path(pages_dir))
            images, warnings = [p.name for p in found], warnings + missing
        system = build_system(no, no in rows)
        out[no] = {"section": no, "rows": no in rows, "method": doc.msds[0].sections[no].method,
                   "lines": len(sent), "preamble_lines": len(sent) - len(span), "first": span[0].id,
                   "last": span[-1].id, "pages": sorted({l.page for l in span}), "images": images,
                   "system": system, "prompt_hash": _hash(system), "system_override": False}
    return {"doc_id": doc_id, "model_tag": model_tag, "model": cfg["model"], "prompt_version": SECTION_PROMPT_VERSION,
            "pages_dir": _rel(pages_dir), "sections_method": doc.sections_method, "msds_count": len(doc.msds),
            "warnings": warnings, "sections": out}


def _public_plan(plan_: dict) -> dict:
    """안내문 글을 뺀 사본 (D-47)."""
    return {**plan_, "sections": {no: {k: v for k, v in s.items() if k != "system"}
                                  for no, s in plan_["sections"].items()}}


# ── 모델 호출 ──────────────────────────────────────────

def _section_result(doc_id: str, no: int, res, first: dict, second: dict | None, system: str, rows: bool) -> dict:
    chosen = second if res.reextracted else first
    raw = {"doc_id": doc_id, "msds_index": 0, "section": no, "reextracted": res.reextracted, **chosen}
    if res.reextracted:
        raw["first_attempt"] = first
    elif second:
        raw["reextract_attempt"] = second
    raw["prompt_hash"] = _hash(system)
    # parse_rows가 버린 줄의 오류는 '<표 이름> <줄 번호> <줄 앞부분>: <문제>'로 시작한다
    tables = row_tables(no) if rows else {}
    dropped = sum(any(e.startswith(f"{t} ") for t in tables) for e in chosen["errors"])
    return {"section": no, "ok": res.ok, "mode": chosen["mode"], "finish_reason": chosen["finish_reason"],
            "raw_text": chosen["raw_text"], "parsed": chosen["parsed"], "dropped_rows": dropped,
            "errors": res.errors, "check_problems": chosen["check_problems"], "seconds": res.seconds,
            "usage": res.usage, "reextracted": res.reextracted, "attempts": res.attempts,
            "prompt_hash": raw["prompt_hash"], "raw": raw}


def run_sections_once(client, cfg: dict, doc, sections: list[int], pages_dir: Path, *,
                      system_override: dict[int, str] | None = None) -> dict[int, dict]:
    """항마다 section_runner._run_section을 그대로 부른다(실패·문제 항 1회 재추출 포함). 항끼리는 동시에 보낸다.
    dropped_rows는 행 형식 응답에서 버린 줄 수(열 수가 안 맞거나 칸 형·검증이 틀린 줄)다.
    system_override의 글은 그 항의 안내문 대신 보내고, 돌려주는 dict에는 해시만 남긴다 (D-47).
    "raw"는 실행기의 raw/<문서>_m0_s<NN>.json과 같은 모양이다."""
    override = system_override or {}
    rows = set(cfg.get("rows_sections") or [])
    jobs = {}
    for no in sections:     # 안내문은 워크북을 읽으므로 스레드에 넘기기 전에 만든다
        system = override[no] if no in override else build_system(no, no in rows)
        images = (sr.section_images(doc, 0, Path(pages_dir))[0]
                  if cfg.get("image_input") and no == sr.IMAGE_SECTION else [])
        jobs[no] = (system, response_schema(no), {l.id for l in section_lines(doc, 0, no)}, no in rows, images)
    with ThreadPoolExecutor(max_workers=sr.workers(cfg)) as pool:
        futures = {no: pool.submit(sr._run_section, client, doc, 0, no, *job, cfg.get("rows_max_tokens"))
                   for no, job in jobs.items()}
    return {no: _section_result(doc.doc_id, no, *futures[no].result(), jobs[no][0], jobs[no][3])
            for no in sections}


def _public_result(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("raw", "raw_text", "parsed")}


# ── 끼워 넣기 채점 ─────────────────────────────────────

def _score(gold: dict, doc: dict) -> dict:
    s = score_pair(gold, doc)
    return {"weighted": s["weighted"], "items": {i["name"]: i["score"] for i in s["items"]}}


def _changed(before: dict, after: dict) -> list[dict]:
    return [{"name": n, "before": before["items"].get(n), "after": a} for n, a in after["items"].items()
            if before["items"].get(n) is None or abs(a - before["items"][n]) > 1e-9]


def patch_and_score(base_run: Path, doc_id: str, new_sections: dict[int, dict], pages_dir: Path, gold_dir: Path, *,
                    sections_dir: Path | None = None, codes_dir: Path | None = None) -> dict:
    """기준 실행 raw/의 채택된 응답(ok인 것만, 실행기와 같다)에 새 항 결과를 끼워 다시 펼치고 정답과 채점한다.
    before는 기준 실행의 outputs/<문서>.json을 그대로 채점한 값이다. 새 결과가 실패면 그 항은 비운다(실행기와 같다).
    새 결과는 첫 건(m0)에만 끼운다. 개발용 10건은 모두 한 건이다."""
    base_run = Path(base_run)
    base_out = _read_json(base_run / "outputs" / f"{doc_id}.json")
    gold = _read_json(Path(gold_dir) / f"{doc_id}.json")
    doc = load_document(doc_id, Path(pages_dir), sections_dir or SECTIONS_DIR, codes_dir or CODES_DIR)
    parts = []
    for i in range(len(base_out["msds"])):
        part = {}
        for no in SECTION_NOS:
            path = base_run / "raw" / f"{doc_id}_m{i}_s{no:02d}.json"
            raw = _read_json(path) if path.exists() else {}
            part[no] = raw.get("parsed") if raw.get("ok") else None
        parts.append(part)
    for no, r in new_sections.items():
        parts[0][no] = r["parsed"] if r["ok"] else None
    patched, _ = to_to21(manifest.get(doc_id), parts, doc.lines, base_out["doc"]["extraction"]["engine"])
    warnings = []
    info = yaml.safe_load((base_run / "run_info.yaml").read_text(encoding="utf-8")) or {}
    if info.get("pages_dir") and (ROOT / info["pages_dir"]).resolve() != Path(pages_dir).resolve():
        warnings.append(f"쪽 글자 폴더가 기준 실행({info['pages_dir']})과 다름: 줄 번호가 어긋날 수 있음")
    before, after = _score(gold, base_out), _score(gold, patched)
    return {"before": before, "after": after, "changed": _changed(before, after), "patched_doc": patched,
            "warnings": warnings}


def pick_base_run(runs_dir: Path, model_tag: str, doc_id: str) -> Path | None:
    """이름에 dev10이 들고 모델 태그가 같고 그 문서 결과가 있는 실행 중 started_at이 가장 늦은 것."""
    found = []
    for run in sorted(Path(runs_dir).iterdir()) if Path(runs_dir).is_dir() else []:
        info_path = run / "run_info.yaml"
        if "dev10" not in run.name or not info_path.exists() or not (run / "outputs" / f"{doc_id}.json").exists():
            continue
        info = yaml.safe_load(info_path.read_text(encoding="utf-8")) or {}
        if info.get("model_tag") == model_tag:
            found.append((str(info.get("started_at") or ""), run.name, run))
    return max(found)[2] if found else None


# ── 기록 ───────────────────────────────────────────────

def save_manual_run(out_dir: Path, doc_id: str, sections: list[int], plan_: dict, results: dict[int, dict],
                    score: dict | None) -> Path:
    """<out_dir>/<YYYYmmdd_HHMMSS>_<문서>_s<항들>/ 에 남긴다. 안내문 글은 쓰지 않는다 (D-47).
    timing.jsonl은 작업 화면의 진행률(b_app_runs)이 이 기록을 끝난 실행으로 읽게 한다. 항끼리 동시에 보내므로
    total은 가장 긴 항의 시간이다. outputs/<문서>.json은 끼워 넣은 TO21 문서이고, 기준 실행이 없으면 쓰지 않는다."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run = Path(out_dir) / f"{stamp}_{doc_id}_s{'_'.join(str(n) for n in sections)}"
    _write_json(run / "plan.json", _public_plan(plan_))
    for no, r in results.items():
        _write_json(run / "raw" / f"{doc_id}_m0_s{no:02d}.json", r["raw"])
    score_out = {k: v for k, v in (score or {}).items() if k != "patched_doc"}
    _write_json(run / "result.json", {"doc_id": doc_id, "sections": sections,
                                      "results": {no: _public_result(r) for no, r in results.items()}, **score_out})
    if score:
        _write_json(run / "outputs" / f"{doc_id}.json", score["patched_doc"])
    timing = [{"doc_id": doc_id, "stage": "call", "msds_index": 0, "section": no, "seconds": r["seconds"],
               "prompt_tokens": r["usage"].get("prompt_tokens"), "completion_tokens": r["usage"].get("completion_tokens")}
              for no, r in results.items()]
    timing.append({"doc_id": doc_id, "stage": "total", "msds_index": None, "section": None,
                   "seconds": max((r["seconds"] for r in results.values()), default=0),
                   "prompt_tokens": None, "completion_tokens": None})
    (run / "timing.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in timing),
                                      encoding="utf-8")
    sr.save_run_info(run, plan_["model_tag"], ROOT / plan_["pages_dir"])
    info_path = run / "run_info.yaml"
    info = yaml.safe_load(info_path.read_text(encoding="utf-8"))
    info["prompt_hashes"].update({no: r["prompt_hash"] for no, r in results.items()})   # 바꾼 안내문의 해시
    info_path.write_text(yaml.safe_dump(info, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return run


# ── 화면 출력 ──────────────────────────────────────────

def fields(m: dict, no: int) -> dict[str, int]:
    """펼친 msds 항목에서 no항이 채우는 칸: 표는 행 수, 객체는 값이 있는 칸 수. 서술·extras는 그 항의 것만 센다."""
    spec = load_specs()[no]
    out = {}
    for t in spec.targets:
        if t == "narratives":
            out[t] = sum(r.get("item_code") in spec.narrative_codes for r in m["narratives"])
        elif t == "meta_revision":
            out["meta"] = sum(m["meta"].get(f) is not None for f in META_REVISION_FIELDS)
        elif isinstance(m.get(t), list):
            out[t] = len(m[t])
        else:
            out[t] = sum(v not in (None, [], {}) for v in (m.get(t) or {}).values())
    out["extras"] = sum(r.get("section_no") == no for r in m.get("extras") or [])
    return out


def _counts(obj: dict, sizes: dict[str, int] | None = None) -> str:
    """'toxicity 3행, product 2칸'. sizes가 없으면 obj에서 센다(객체 칸의 lines는 세지 않는다)."""
    sizes = sizes or {k: len(v) if isinstance(v, list) else sum(x not in (None, [], {}) for k2, x in v.items()
                                                                 if k2 != "lines")
                      for k, v in obj.items() if isinstance(v, (list, dict))}
    return ", ".join(f"{k} {n}{'행' if isinstance(obj.get(k), list) else '칸'}" for k, n in sizes.items())


def _pct(v) -> str:
    return "-" if v is None else f"{v * 100:.1f}"


def _print_plan(p: dict, show_prompt: bool) -> None:
    print(f"== ① 보낸 입력: {p['doc_id']}, {p['model_tag']} ({p['model']}), 쪽 글자 {p['pages_dir']}, "
          f"항목 분할 {p['sections_method']}, MSDS {p['msds_count']}건(첫 건만)")
    for no, s in p["sections"].items():
        images = ", ".join(s["images"]) or "없음"
        print(f"{no}항  {'행 형식' if s['rows'] else 'JSON'}  줄 {s['lines']} (머리 {s['preamble_lines']})  "
              f"{s['first']} ~ {s['last']} ({s['method']})  쪽 {', '.join(map(str, s['pages']))}  이미지 {images}")
    for w in p["warnings"]:
        print(f"  경고: {w}")
    print(f"== ② 안내문 ({p['prompt_version']})")
    for no, s in p["sections"].items():
        mark = "  바꾼 안내문" if s["system_override"] else ""
        print(f"{no}항  해시 {s['prompt_hash']}  {len(s['system']):,}자{mark}")
        if show_prompt:
            print(f"--- {no}항 안내문 ---\n{s['system'].rstrip()}\n--- 끝 ---")


def _print_results(results: dict[int, dict]) -> None:
    print("== ③ 모델 원문 답")
    for no, r in results.items():
        print(f"--- {no}항 ({r['mode']}, {r['finish_reason']}, {r['seconds']:.1f}초) ---")
        lines = (r["raw_text"] or "(응답 없음)").splitlines()
        print("\n".join(lines[:ANSWER_LINES]))
        if len(lines) > ANSWER_LINES:
            print(f"…({len(lines) - ANSWER_LINES}줄 더)")
    print("== ④ 읽은 결과")
    for no, r in results.items():
        got = _counts(r["parsed"]) if r["parsed"] else "읽은 것 없음"
        print(f"{no}항  {'성공' if r['ok'] else '실패'}  {got}  버린 줄 {r['dropped_rows']}  "
              f"{'재추출 결과' if r['reextracted'] else '첫 시도'}  시도 {r['attempts']}  "
              f"입력 {r['usage'].get('prompt_tokens')} / 출력 {r['usage'].get('completion_tokens')} 토큰")
        for e in r["errors"]:
            print(f"  오류: {e}")
        for e in r["check_problems"]:
            print(f"  줄 번호 검사: {e}")


def _print_score(score: dict | None, base_run: Path | None, gold_dir: Path, reason: str | None) -> None:
    if score is None:
        print(f"== ⑥ 점수: 건너뜀 ({reason})")
        return
    print(f"== ⑥ 점수 전 → 후 (기준 실행 {_rel(base_run)}, 정답 {_rel(gold_dir)})")
    print(f"가중 종합 {score['before']['weighted']:.1f} → {score['after']['weighted']:.1f}")
    for c in score["changed"]:
        print(f"{c['name']} {_pct(c['before'])} → {_pct(c['after'])}")
    if not score["changed"]:
        print("바뀐 항목 없음")
    for w in score.get("warnings") or []:
        print(f"  경고: {w}")


# ── 명령줄 ─────────────────────────────────────────────

def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="항 하나·여러 개·문서 전체를 모델에 보내고 단계별로 보여 준다 (개발 전용)")
    ap.add_argument("--model", required=True, help="configs/models.yaml의 태그")
    ap.add_argument("--doc", required=True, help="문서 번호. 평가용 문서는 받지 않는다 (D-43)")
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--section", type=int, action="append", choices=SECTION_NOS, help="항 번호. 여러 번 줄 수 있다")
    which.add_argument("--all", action="store_true", help="문서 전체(16개 항)를 실행기로 돌린다")
    ap.add_argument("--pages-dir", type=Path, default=PAGES, help="쪽 글자 폴더 (없으면 data/pages)")
    ap.add_argument("--dry-run", action="store_true", help="① 보낸 입력과 ② 안내문만 보이고 서버를 부르지 않는다")
    ap.add_argument("--system-file", type=Path, help="이 글을 안내문 대신 보낸다. --section 하나일 때만. 기록에는 해시만")
    ap.add_argument("--base-run", help="끼워 넣을 기준 실행 이름 (없으면 같은 모델의 가장 최근 dev10 실행)")
    ap.add_argument("--gold-dir", type=Path, help="정답 폴더 (없으면 data/silver/claude)")
    ap.add_argument("--out-dir", type=Path, help="기록 폴더 (없으면 runs/manual)")
    ap.add_argument("--json", action="store_true", help="같은 내용을 JSON 한 덩이로 찍는다 (안내문 글은 빼고 해시만)")
    ap.add_argument("--show-prompt", action="store_true", help="② 안내문 전문을 찍는다 (화면에만)")
    return ap


def _base_run(name: str | None, model_tag: str, doc_id: str) -> Path | None:
    if not name:
        return pick_base_run(RUNS, model_tag, doc_id)
    return Path(name) if Path(name).is_dir() else RUNS / name


def _run_all(a, cfg: dict, p: dict, gold_dir: Path, out_dir: Path, base: Path | None) -> dict:
    """문서 전체를 실행기로 돌리고 step 0의 summarize_run으로 채점한다. 기준 실행이 있으면 바뀐 항목도 낸다."""
    from b_app_runs import summarize_run    # 개발 전용 채점 요약 (msds.evaluate)

    name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{a.doc}_all"
    run = out_dir / name
    sr.save_run_info(run, a.model, a.pages_dir)
    res = sr.run_document(a.doc, a.model, name, ChatClient(cfg), pages_dir=a.pages_dir, sections_dir=SECTIONS_DIR,
                          codes_dir=CODES_DIR, runs_dir=out_dir)
    summary = summarize_run(run, gold_dir, cache_dir=None)
    score = None
    gold_path = gold_dir / f"{a.doc}.json"
    if base and gold_path.exists():
        gold = _read_json(gold_path)
        before, after = _score(gold, _read_json(base / "outputs" / f"{a.doc}.json")), \
            _score(gold, _read_json(run / "outputs" / f"{a.doc}.json"))
        score = {"before": before, "after": after, "changed": _changed(before, after)}
    return {"plan": _public_plan(p), "run": res, "summary": summary, "score": score,
            "base_run": str(base) if base else None, "saved": str(run)}


def main(argv: list[str] | None = None) -> int:
    ap = _parser()
    a = ap.parse_args(argv)
    if a.system_file and (a.all or len(a.section) != 1):
        ap.error("--system-file은 --section 하나와 함께만 쓴다")
    sections = list(SECTION_NOS) if a.all else sorted(set(a.section))
    try:
        p = plan(a.doc, a.model, sections, a.pages_dir)
    except (KeyError, ValueError) as e:
        ap.error(e.args[0])
    override = {}
    if a.system_file:
        override = {sections[0]: a.system_file.read_text(encoding="utf-8")}
        p["sections"][sections[0]].update(system=override[sections[0]], prompt_hash=_hash(override[sections[0]]),
                                          system_override=True)
    if not a.json:
        _print_plan(p, a.show_prompt)
    if a.dry_run:
        if a.json:
            print(json.dumps({"plan": _public_plan(p)}, ensure_ascii=False, indent=1))
        return 0

    cfg = load_model_config(a.model)
    gold_dir = a.gold_dir or SILVER / "claude"
    out_dir = a.out_dir or RUNS / "manual"
    base = _base_run(a.base_run, a.model, a.doc)
    if a.all:
        t0 = time.perf_counter()
        out = _run_all(a, cfg, p, gold_dir, out_dir, base)
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
            return 0
        s = out["summary"]
        print(f"== 문서 전체 ({time.perf_counter() - t0:.0f}초): 성공 {out['run']['sections_ok']}항, "
              f"실패 {out['run']['sections_failed']}항, 재추출 {out['run']['reextracted']}항")
        if s.get("weighted") is not None:
            print(f"가중 종합 {s['weighted']:.1f}, 필수 통과 {s['must_passed']}/{s['must_total']}")
        _print_score(out["score"], base, gold_dir, "기준 실행이나 정답이 없음")
        print(f"기록: {_rel(out['saved'])}")
        return 0

    client = ChatClient(cfg)
    doc = load_document(a.doc, a.pages_dir, SECTIONS_DIR, CODES_DIR)
    results = run_sections_once(client, cfg, doc, sections, a.pages_dir, system_override=override)
    score, reason = None, None
    if base is None:
        reason = f"기준 실행 없음: 이름에 dev10이 든 {a.model} 실행에 {a.doc} 결과가 없다"
    elif not (gold_dir / f"{a.doc}.json").exists():
        reason = f"정답 없음: {_rel(gold_dir / f'{a.doc}.json')}"
    else:
        score = patch_and_score(base, a.doc, results, a.pages_dir, gold_dir)
    if score:
        m = score["patched_doc"]["msds"][0]
    else:     # 기준 실행 없이 새 항만 펼친다. ⑤에만 쓰고 outputs/에는 쓰지 않는다
        parts = [{no: (results[no]["parsed"] if no in results and results[no]["ok"] else None) for no in SECTION_NOS}]
        m = to_to21(manifest.get(a.doc), parts, doc.lines, f"{a.model}:{cfg['model']}")[0]["msds"][0]
    filled = {no: fields(m, no) for no in sections}
    saved = save_manual_run(out_dir, a.doc, sections, p, results, score)

    if a.json:
        print(json.dumps({"plan": _public_plan(p),
                          "results": {no: {k: v for k, v in r.items() if k != "raw"} for no, r in results.items()},
                          "fields": filled, "base_run": str(base) if base else None,
                          "score": {k: v for k, v in score.items() if k != "patched_doc"} if score else None,
                          "score_skipped": reason, "saved": str(saved)}, ensure_ascii=False, indent=1))
        return 0
    _print_results(results)
    print("== ⑤ 펼친 TO21 칸" + ("" if score else " (기준 실행 없이 이 항만 펼침)"))
    for no, f in filled.items():
        print(f"{no}항  {_counts(m, f)}")
    _print_score(score, base, gold_dir, reason)
    print(f"기록: {_rel(saved)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
