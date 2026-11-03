"""같은 문서를 같은 조건으로 N회 돌려 응답이 흔들리는지 잰다 (결정성 시험, 11/3).

사용법 (backend/에서. 모델 서버는 미리 띄운다: scripts/pod_up.py --tag <태그>)
  python scripts/repeat_runs.py --tag qwen36_35b_runpod_48g_det --docs T21-S003 T21-S016 \
      --rounds 3 --concurrency 8 --name det_c8 --gpu "RTX 6000 Ada" --pages-dir ../../to21-msds-poc/data/pages
  --parallel-docs  문서들을 동시에 보낸다 (여러 사용자가 함께 쓰는 상황)
  --concurrency    문서 하나의 항목별 동시 호출 수. 없으면 태그의 concurrency

결과
  runs/<날짜>_repeat_<이름>_r<i>/      회차마다 실행 폴더 (section_runner와 같은 모양)
  runs/<날짜>_repeat_<이름>/repeat.md  항별 원문이 회차마다 같은지, 달라진 TO21 칸, 시간
                                        repeat.json  같은 내용의 기계용
  정답(실버)이 있는 문서는 compare_models로 점수도 낸다 (runs/<날짜>_models_repeat_<이름>/).
외부 연결은 모델 서버뿐이다. 회사 GPU에서도 그대로 돌린다.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from _common import today
from msds.common import paths
from msds.extract.client import load_model_config

IGNORED_FIELDS = ("doc.extraction.extracted_at",)   # 회차마다 다른 것이 당연한 칸
SNIPPET = 40          # 첫 차이 앞뒤로 보여 줄 글자 수
EXAMPLES = 15         # 보고서에 보여 줄 달라진 칸 수


@dataclass(frozen=True)
class Plan:
    tag: str
    docs: list[str]
    rounds: int
    concurrency: int
    name: str
    parallel_docs: bool = False


@dataclass
class RunOutcome:
    run_dirs: list[Path]
    seconds: dict[str, list[float | None]]
    errors: dict[tuple[str, str], str] = field(default_factory=dict)


# ── 비교 ──

def flat(obj, prefix: str = ""):
    """중첩 dict·list를 (경로, 값)으로 편다. 경로는 msds[0].components[1].cas 모양."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flat(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flat(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def _first_diff(a: str, b: str) -> tuple[str, str]:
    i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    lo = max(0, i - SNIPPET)
    return a[lo:i + SNIPPET], b[lo:i + SNIPPET]


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def compare_doc(run_dirs: list[Path], doc: str) -> dict:
    """회차 폴더들에서 문서 하나를 비교한다. 항은 응답 원문(raw_text) 그대로, 결과는 펼친 TO21 칸 단위로."""
    names = sorted({p.name for r in run_dirs for p in (Path(r) / "raw").glob(f"{doc}_m*_s*.json")})
    sections = []
    for name in names:
        recs = [_read(Path(r) / "raw" / name) for r in run_dirs]
        present = [x for x in recs if x is not None]
        texts = [x.get("raw_text") or "" for x in present]
        same = len(present) == len(recs) and len(set(texts)) == 1
        item = {"msds_index": present[0]["msds_index"], "section": present[0]["section"], "same": same,
                "missing": [x is None for x in recs],
                "tokens": [(x.get("usage") or {}).get("completion_tokens") if x else None for x in recs],
                "reextracted": [x.get("reextracted") if x else None for x in recs],
                "ok": [x.get("ok") if x else None for x in recs]}
        if not same and len(set(texts)) > 1:
            other = next(t for t in texts[1:] if t != texts[0])
            item["first_diff"] = list(_first_diff(texts[0], other))
        sections.append(item)
    sections.sort(key=lambda s: (s["msds_index"], s["section"]))

    outs = [_read(Path(r) / "outputs" / f"{doc}.json") for r in run_dirs]
    flats = [dict(flat(o)) for o in outs if o is not None]
    keys = sorted(set().union(*flats) - set(IGNORED_FIELDS)) if flats else []
    diff = [k for k in keys if len({json.dumps(f.get(k), ensure_ascii=False) for f in flats}) > 1]
    return {"doc": doc, "sections": sections, "outputs_missing": [o is None for o in outs],
            "fields_total": len(keys), "fields_diff": len(diff),
            "diff_examples": [{"field": k, "values": [f.get(k) for f in flats]} for k in diff[:EXAMPLES]]}


# ── 실행 ──

def run_all(plan: Plan, *, runs_dir: Path, pages_dir: Path, sections_dir: Path, extract: Callable | None = None,
            save_info: Callable | None = None, log=print) -> RunOutcome:
    """회차마다 문서들을 돌린다. 한 문서가 실패해도 기록하고 다음으로 간다."""
    if extract is None or save_info is None:
        from msds.extract.section_runner import run_document, save_run_info
        extract, save_info = extract or run_document, save_info or save_run_info
    out = RunOutcome(run_dirs=[], seconds={d: [] for d in plan.docs})

    def one(doc: str, run_name: str) -> float | None:
        t = time.perf_counter()
        try:
            extract(doc, plan.tag, run_name, max_workers=plan.concurrency, pages_dir=pages_dir,
                    sections_dir=sections_dir, runs_dir=runs_dir)
        except Exception as e:   # 모델 서버·입력 문제 무엇이든 기록하고 남은 문서를 계속 돈다
            out.errors[(doc, run_name)] = f"{type(e).__name__}: {e}"
            log(f"  {doc} {run_name} 실패: {type(e).__name__}: {str(e)[:200]}")
            return None
        sec = round(time.perf_counter() - t, 1)
        log(f"  {doc} {run_name} {sec}초")
        return sec

    for i in range(1, plan.rounds + 1):
        run_name = f"{plan.name}_r{i}"
        run = Path(runs_dir) / run_name
        out.run_dirs.append(run)
        save_info(run, plan.tag, pages_dir, max_workers=plan.concurrency)
        log(f"[{i}/{plan.rounds}] {run_name}")
        if plan.parallel_docs:
            with ThreadPoolExecutor(max_workers=len(plan.docs)) as pool:
                secs = list(pool.map(lambda d: one(d, run_name), plan.docs))
        else:
            secs = [one(d, run_name) for d in plan.docs]
        for d, s in zip(plan.docs, secs):
            out.seconds[d].append(s)
    return out


# ── 보고서 ──

def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "⏎")


def write_report(plan: Plan, out: RunOutcome, report_dir: Path, *, server: dict, gpu: str | None) -> Path:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    docs = {d: compare_doc(out.run_dirs, d) for d in plan.docs}
    for d, res in docs.items():
        res["sections_same"] = sum(s["same"] for s in res["sections"])
        res["seconds"] = out.seconds.get(d, [])

    lines = [f"# 반복 실행 비교: {plan.name}", "",
             f"- 모델 태그: `{plan.tag}`, GPU: {gpu or '기록 안 함'}",
             f"- 서버 설정: {', '.join(f'{k}={v}' for k, v in server.items()) or '기본'}",
             f"- 회차 {plan.rounds}, 문서 하나의 항목별 동시 호출 {plan.concurrency}, "
             f"문서 동시 처리 {'예' if plan.parallel_docs else '아니오'}",
             f"- 회차 폴더: {', '.join(r.name for r in out.run_dirs)}", "",
             "## 요약", "",
             "| 문서 | 원문이 같은 항 | 다른 TO21 칸 | 시간(초, 회차별) | 실패 |", "|---|---|---|---|---|"]
    for d, res in docs.items():
        n = len(res["sections"])
        failed = [r.name for r in out.run_dirs if (d, r.name) in out.errors]
        lines.append(f"| {d} | {res['sections_same']}/{n} | {res['fields_diff']}/{res['fields_total']} | "
                     f"{' / '.join('-' if s is None else str(s) for s in res['seconds'])} | {', '.join(failed) or '-'} |")
    lines += ["", "TO21 칸 수는 표에 행이 하나 끼면 뒤 행이 모두 밀려 다르게 세어지므로 실제보다 크게 나온다. "
              "추출 시각 칸은 세지 않는다.", ""]
    for d, res in docs.items():
        lines += [f"## {d}", "", "| 건 | 항 | 원문 | 출력 토큰 | 재추출 | 첫 차이 (1회차 \\| 다른 회차) |",
                  "|---|---|---|---|---|---|"]
        for s in res["sections"]:
            diff = " \\| ".join(_cell(x) for x in s.get("first_diff", [])) or ("없는 회차 있음" if any(s["missing"]) else "")
            lines.append(f"| {s['msds_index']} | {s['section']} | {'같음' if s['same'] else '다름'} | "
                         f"{s['tokens']} | {s['reextracted']} | {diff} |")
        if res["diff_examples"]:
            lines += ["", "달라진 칸 (앞에서부터):", ""]
            lines += [f"- `{e['field']}`: {_cell(json.dumps(e['values'], ensure_ascii=False))[:300]}"
                      for e in res["diff_examples"]]
        lines.append("")
    if out.errors:
        lines += ["## 실패", ""] + [f"- {d} {r}: {_cell(msg)[:300]}" for (d, r), msg in out.errors.items()] + [""]

    path = report_dir / "repeat.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    result = {"plan": plan.__dict__, "server": server, "gpu": gpu, "run_dirs": [r.name for r in out.run_dirs],
              "errors": {f"{d} {r}": m for (d, r), m in out.errors.items()}, "docs": docs}
    (report_dir / "repeat.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def _score(plan: Plan, out: RunOutcome) -> None:
    """정답이 있는 문서만 점수를 낸다. 없으면 건너뛴다."""
    import compare_models
    gold = paths.SILVER / "claude"
    docs = [d for d in plan.docs if (gold / f"{d}.json").is_file()]
    if not docs:
        print("정답(실버)이 있는 문서가 없어 점수는 내지 않습니다.")
        return
    try:
        compare_models.main(["--title", f"repeat_{plan.name}", "--docs", *docs,
                             "--runs", *[f"r{i + 1}={r.name}" for i, r in enumerate(out.run_dirs)]])
    except Exception:   # 점수 집계가 실패해도 반복 비교 결과는 남긴다
        print("점수 집계 실패:\n" + traceback.format_exc(limit=3), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="같은 문서를 N회 돌려 응답이 흔들리는지 잰다")
    ap.add_argument("--tag", required=True, help="configs/models.yaml의 모델 태그")
    ap.add_argument("--docs", nargs="+", required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--concurrency", type=int, help="문서 하나의 항목별 동시 호출 수 (없으면 태그 값)")
    ap.add_argument("--name", required=True, help="실행 이름. runs/<날짜>_repeat_<이름>_r<i>")
    ap.add_argument("--parallel-docs", action="store_true", help="문서들을 동시에 보낸다")
    ap.add_argument("--gpu", help="보고서에 남길 GPU 이름")
    ap.add_argument("--pages-dir", type=Path, default=paths.PAGES)
    ap.add_argument("--sections-dir", type=Path, default=paths.DATA / "sections")
    ap.add_argument("--no-score", action="store_true", help="실버 점수를 내지 않는다")
    args = ap.parse_args(argv)
    if args.rounds < 1:
        ap.error("--rounds는 1 이상")

    cfg = load_model_config(args.tag)
    plan = Plan(tag=args.tag, docs=args.docs, rounds=args.rounds, concurrency=args.concurrency or cfg.get("concurrency") or 16,
                name=f"{today()}_repeat_{args.name}", parallel_docs=args.parallel_docs)
    out = run_all(plan, runs_dir=paths.RUNS, pages_dir=args.pages_dir.resolve(), sections_dir=args.sections_dir.resolve())
    report = write_report(plan, out, paths.RUNS / plan.name, server=cfg.get("server") or {}, gpu=args.gpu)
    print(f"비교: {report}")
    if not args.no_score:
        _score(plan, out)
    return 1 if out.errors else 0


if __name__ == "__main__":
    sys.exit(main())
