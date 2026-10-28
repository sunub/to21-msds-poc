"""모델 비교 집계 (역할 B, ADR-013): 실행 폴더 여러 개 × 정답 자리(Claude 실버) → 비교표

사용법 (라벨=실행 이름, 라벨은 생략할 수 있다)
  python scripts/compare_models.py --title 세모델 \
      --runs qwen30=20261028_sections_qwen3_30b_a3b_rngd gptoss=20261028_sections_gpt_oss_20b_rngd
  python scripts/compare_models.py --title 시험 --runs a=run_a b=run_b --docs T21-S003 T21-S016

결과: runs/<날짜>_models_<제목>/compare.md, result.json
점수 계산은 F의 msds.evaluate.score(score_set, score_pair)를 그대로 부른다. 평가용 문서는 받지 않는다 (D-43).
"""
import argparse
import json
import os
import statistics
from pathlib import Path

import yaml

from _common import today
from msds.common import manifest, paths
from msds.evaluate.score import score_pair, score_set
from msds.extract.section_runner import DOC_TIME_LIMIT

TABLES = ("components", "exposure_limits", "physchem", "toxicity", "cmr", "ecotox", "regulations", "intl_class")
VALUE_ITEMS = ("H 코드", "P 코드", "구성성분(CAS", "함유량")   # 채점 항목 이름의 앞부분
ROW_KEYS = TABLES + ("extras",)
NOTES = ("정답 자리 파일이 실버라면 점수는 순위 비교용이다. 합격 판정에 쓰지 않는다.",
         "그림문자는 이미지 모델 전이라 모든 실행이 0점이다.")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_run(run: Path, label: str | None = None) -> dict:
    run = Path(run)
    info = yaml.safe_load((run / "run_info.yaml").read_text(encoding="utf-8")) or {}
    outputs = {p.stem: _read_json(p) for p in sorted((run / "outputs").glob("*.json"))}
    checks = {p.stem: _read_json(p) for p in sorted((run / "checks").glob("*.json"))}
    seconds: dict[str, float] = {}
    timing = run / "timing.jsonl"
    if timing.exists():
        for line in timing.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("stage") == "total":
                seconds[rec["doc_id"]] = rec["seconds"]          # 같은 문서 줄이 여럿이면 마지막 줄
    return {"label": label or run.name, "name": run.name, "model_tag": info.get("model_tag"),
            "prompt_version": info.get("prompt_version"), "pages_dir": info.get("pages_dir"),
            "outputs": outputs, "checks": checks, "seconds": seconds}


def row_counts(doc: dict) -> dict[str, int]:
    counts = dict.fromkeys(ROW_KEYS, 0)
    for m in doc.get("msds", []):
        for k in ROW_KEYS:
            counts[k] += len(m.get(k) or [])
    return counts


def select_docs(runs: list[dict], gold_dir: Path, docs: list[str] | None = None) -> tuple[list[str], list[dict]]:
    have = [set(r["outputs"]) for r in runs]
    candidates = set.intersection(*have) if have else set()
    universe = set(docs) if docs else set.union(*have, set())
    candidates &= universe
    excluded = []
    for d in sorted(universe - candidates):
        lacking = [r["label"] for r in runs if d not in r["outputs"]]
        excluded.append({"doc_id": d, "reason": f"결과 없음: {', '.join(lacking)}"})
    check = sorted(candidates | set(docs or []))
    if check:
        evals = [r["doc_id"] for r in manifest.select(None, check) if r["purpose"] == "평가"]
        if evals:
            raise ValueError(f"평가용 문서는 비교에 쓸 수 없습니다({', '.join(evals)}). 평가용 채점은 F의 score.py로 합니다 (D-43)")
    scored = []
    for d in sorted(candidates):
        if (Path(gold_dir) / f"{d}.json").exists():
            scored.append(d)
        else:
            excluded.append({"doc_id": d, "reason": "정답 없음"})
    return scored, excluded


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def _range(xs):
    return max(xs) - min(xs)


def _run_summary(run: dict, golds: dict, docs: list[str], per_doc: dict) -> dict:
    pairs = [(d, golds[d], run["outputs"][d]) for d in docs]
    ss = score_set(pairs)
    items = {i["name"]: i["score"] for i in ss["items"]}
    value = [s for n, s in items.items() if n.startswith(VALUE_ITEMS)]
    pred_rows = {d: row_counts(run["outputs"][d]) for d in docs}
    gold_rows = {d: row_counts(golds[d]) for d in docs}
    rows = {}
    for k in ROW_KEYS:
        p, g = sum(pred_rows[d][k] for d in docs), sum(gold_rows[d][k] for d in docs)
        rows[k] = {"pred": p, "gold": g, "ratio": p / g if g else None}
    secs = [run["seconds"][d] for d in docs if d in run["seconds"]]
    doc_info = {}
    for d in docs:
        c = run["checks"].get(d, {})
        doc_info[d] = {"weighted": ss["docs"][d]["weighted"], "seconds": run["seconds"].get(d),
                       "sections_failed": sum(1 for s in c.get("sections", []) if not s.get("ok")),
                       "validator_errors": len(c.get("to21_validator") or []),
                       "schema_errors": len(c.get("schema_errors") or [])}
    per_doc[run["label"]] = {d: {i["name"]: i["score"] for i in score_pair(golds[d], run["outputs"][d])["items"]}
                             for d in docs}
    return {
        "label": run["label"], "name": run["name"], "model_tag": run["model_tag"],
        "prompt_version": run["prompt_version"], "pages_dir": run["pages_dir"],
        "weighted": ss["weighted"], "must_passed": ss["must_passed_count"], "must_total": ss["must_total"],
        "value_score": _mean(value),
        "items": items,
        "levels": {i["name"]: i["level"] for i in ss["items"]},
        "targets": {i["name"]: i["target"] for i in ss["items"]},
        "rows": rows,
        "time": {"median": statistics.median(secs) if secs else None, "max": max(secs) if secs else None,
                 "over_limit": sum(1 for s in secs if s > DOC_TIME_LIMIT)},
        "sections_failed": sum(v["sections_failed"] for v in doc_info.values()),
        "validator_errors": sum(v["validator_errors"] for v in doc_info.values()),
        "schema_errors": sum(v["schema_errors"] for v in doc_info.values()),
        "docs": {d: {k: v[k] for k in ("weighted", "seconds", "sections_failed", "validator_errors")}
                 for d, v in doc_info.items()},
        "_rows_by_doc": pred_rows,
    }


def _group_summary(key: tuple, members: list[dict], per_doc: dict, docs: list[str]) -> dict:
    g = {"model_tag": key[0], "prompt_version": key[1], "pages_dir": key[2],
         "runs": [m["label"] for m in members],
         "weighted_mean": _mean(m["weighted"] for m in members),
         "value_mean": _mean(m["value_score"] for m in members),
         "spread": None, "doc_weighted_spread": None, "item_spread": {}, "row_spread": {}}
    if len(members) < 2:
        return g
    names = list(members[0]["items"])
    for n in names:
        g["item_spread"][n] = _mean(_range([per_doc[m["label"]][d][n] for m in members]) for d in docs)
    g["spread"] = _mean(_range([per_doc[m["label"]][d][n] for m in members]) for d in docs for n in names)
    g["doc_weighted_spread"] = _mean(_range([m["docs"][d]["weighted"] for m in members]) for d in docs)
    g["row_spread"] = {k: sum(_range([m["_rows_by_doc"][d][k] for m in members]) for d in docs) for k in ROW_KEYS}
    return g


def compare_runs(runs: list[dict], golds: dict[str, dict], docs: list[str]) -> dict:
    per_doc: dict[str, dict] = {}
    summaries = [_run_summary(r, golds, docs, per_doc) for r in runs]
    keys: dict[tuple, list[dict]] = {}
    for r, s in zip(runs, summaries):
        keys.setdefault((r["model_tag"], r["prompt_version"], r["pages_dir"]), []).append(s)
    groups = [_group_summary(k, m, per_doc, docs) for k, m in keys.items()]
    for s in summaries:
        del s["_rows_by_doc"]
    return {"docs": list(docs), "runs": summaries, "groups": groups}


def _pct(x) -> str:
    return "-" if x is None else f"{x * 100:.1f}"


def _num(x, digits=1) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


def _table(head: list[str], body: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in body]
    return out + [""]


def write_compare(result: dict, out_dir: Path, title: str) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps({**result, "title": title}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    runs, groups = result["runs"], result["groups"]
    labels = [r["label"] for r in runs]
    lines = [f"# 모델 비교: {title}", "",
             f"- 정답 자리: {result.get('gold_dir')}",
             f"- 채점 문서 {len(result['docs'])}건: {', '.join(result['docs'])}"]
    if result.get("excluded"):
        lines += ["- 빠진 문서:"] + [f"  - {e['doc_id']}: {e['reason']}" for e in result["excluded"]]
    lines += ["", "## 실행별 요약", ""]
    lines += _table(
        ["라벨", "모델 태그", "가중 종합", "필수 통과", "값 칸(%)", "시간 중앙값(초)", "시간 최대(초)",
         f"{DOC_TIME_LIMIT}초 초과", "실패 항목", "검증기 오류"],
        [[r["label"], r["model_tag"], _num(r["weighted"]), f"{r['must_passed']}/{r['must_total']}",
          _pct(r["value_score"]), _num(r["time"]["median"], 0), _num(r["time"]["max"], 0), r["time"]["over_limit"],
          r["sections_failed"], r["validator_errors"]] for r in runs])
    lines += ["## 조건 묶음", ""]
    lines += _table(
        ["묶음", "모델 태그", "안내문 버전", "쪽 글자 폴더", "실행 수", "가중 종합 평균", "값 칸 평균(%)",
         "전체 흔들림(%p)", "문서 가중 종합 흔들림(점)"],
        [[i + 1, g["model_tag"], g["prompt_version"], g["pages_dir"], len(g["runs"]), _num(g["weighted_mean"]),
          _pct(g["value_mean"]), _pct(g["spread"]), _num(g["doc_weighted_spread"])] for i, g in enumerate(groups)])
    spread_groups = [(i + 1, g) for i, g in enumerate(groups) if g["spread"] is not None]
    lines += ["## 항목별 점수 (%)", ""]
    first = runs[0]
    lines += _table(
        ["중요도", "항목"] + labels + [f"흔들림 묶음{i}(%p)" for i, _ in spread_groups],
        [[first["levels"][n], n] + [_pct(r["items"][n]) for r in runs] + [_pct(g["item_spread"][n]) for _, g in spread_groups]
         for n in first["items"]])
    lines += ["## 표 행 수 (결과/정답 (비율))", ""]
    body = []
    for k in ROW_KEYS:
        cells = []
        for r in runs:
            v = r["rows"][k]
            cells.append(f"{v['pred']}/{v['gold']} ({_pct(v['ratio'])}%)" if v["ratio"] is not None
                         else f"{v['pred']}/{v['gold']}")
        body.append([k] + cells + [g["row_spread"][k] for _, g in spread_groups])
    lines += _table(["표"] + labels + [f"행 수 흔들림 묶음{i}" for i, _ in spread_groups], body)
    lines += ["## 문서별 (가중 종합 / 시간 초)", ""]
    lines += _table(["문서"] + labels,
                    [[d] + [f"{_num(r['docs'][d]['weighted'])} / {_num(r['docs'][d]['seconds'], 0)}" for r in runs]
                     for d in result["docs"]])
    lines += ["## 주의", ""] + [f"- {n}" for n in NOTES]
    out = out_dir / "compare.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> Path:
    ap = argparse.ArgumentParser(description="실행 폴더 여러 개를 정답 자리와 비교해 비교표를 쓴다")
    ap.add_argument("--title", required=True)
    ap.add_argument("--runs", nargs="+", required=True, metavar="[라벨=]실행이름")
    ap.add_argument("--docs", nargs="*", help="채점할 문서를 좁힌다")
    ap.add_argument("--gold-dir", type=Path, help="정답 폴더 (없으면 data/silver/claude)")
    a = ap.parse_args(argv)
    gold_dir = a.gold_dir or paths.SILVER / "claude"
    runs = []
    for spec in a.runs:
        label, name = spec.split("=", 1) if "=" in spec else (spec, spec)
        folder = paths.run_dir(name)
        if not (folder / "run_info.yaml").exists():
            ap.error(f"실행 폴더나 run_info.yaml이 없습니다: {folder}")
        runs.append(load_run(folder, label))
    try:
        docs, excluded = select_docs(runs, gold_dir, a.docs)
    except (KeyError, ValueError) as e:
        ap.error(e.args[0])
    if not docs:
        ap.error("채점할 문서가 없습니다. 빠진 문서: " + "; ".join(f"{e['doc_id']}({e['reason']})" for e in excluded))
    golds = {d: _read_json(gold_dir / f"{d}.json") for d in docs}
    result = {"title": a.title, "gold_dir": os.path.relpath(gold_dir, paths.ROOT), "excluded": excluded,
              **compare_runs(runs, golds, docs)}
    out = write_compare(result, paths.run_dir(f"{today()}_models_{a.title}"), a.title)
    for r in result["runs"]:
        print(f"{r['label']}: 가중 종합 {r['weighted']:.1f}, 필수 {r['must_passed']}/{r['must_total']}, "
              f"값 칸 {_pct(r['value_score'])}%")
    print(out)
    return out


if __name__ == "__main__":
    main()
