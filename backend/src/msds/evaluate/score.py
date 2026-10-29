"""성적표 — 역할 F (D-1, D-13, D-35).

공식 점수는 TO21 채점기 그대로다(채점기는 고치지 않는다). 이 모듈은 그 위에서
문서 여러 건을 돌려 평균을 내고, '왜 틀렸는지'(빠뜨림·지어냄·틀림)를 함께 정리한다.

- score_pair(gold, pred)        문서 한 건 채점 (TO21 채점기 23개 항목)
- score_set([(문서, 골드, 결과)]) 여러 건: 항목별 문서 평균 → 가중 종합 점수 → 합격 판정
- write_report(result, 폴더, 제목) 성적표 파일 (report.md, items.csv, docs.csv, details.csv, result.json)

합격 기준: 필수 17개가 모두 목표 이상 + 가중 종합 90점 이상 (가중치 필수 3 · 중요 2 · 일반 1)
완료 확인: pytest tests/test_F_score.py
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from ..checks.validator import load_to21_module
from ..common import paths

WEIGHTS = {"필수": 3, "중요": 2, "일반": 1}
LEVEL_ORDER = {"필수": 0, "중요": 1, "일반": 2}
PASS_SCORE = 90.0

# 채점기 상세의 종류 → D-13 이름
KIND = {"누락": "빠뜨림", "오추출": "지어냄", "불일치": "틀림"}
KINDS = ("빠뜨림", "지어냄", "틀림")

# 미검수 칸의 최상위 키 → 영향을 받는 채점 항목(이름 앞부분). D-35 '참고' 표시에 쓴다
TOP_TO_ITEMS = {
    "doc": ["MSDS 건수"],
    "meta": ["관리정보"],
    "product": ["제품명"],
    "companies": ["제품명"],
    "hazard": ["신호어", "그림문자", "H 코드", "P 코드", "유해성 분류"],
    "composition": ["구성성분", "함유량"],
    "components": ["구성성분", "함유량"],
    "exposure_limits": ["8항"],
    "physchem": ["9항"],
    "toxicity": ["11항 급성", "11항 기타"],
    "cmr": ["11항 CMR"],
    "ecotox": ["12항"],
    "regulations": ["15항"],
    "transport": ["14항"],
    "narratives": ["서술형"],
}


def _weighted(items: list[dict]) -> float:
    total = sum(WEIGHTS[i["level"]] for i in items)
    return sum(WEIGHTS[i["level"]] * i["score"] for i in items) / total * 100 if total else 0.0


def score_pair(gold: dict, pred: dict) -> dict:
    """문서 한 건 채점. TO21 채점기의 23개 항목과 필수 항목 오류 상세를 돌려준다."""
    sc = load_to21_module("scorer")
    rows = sc.score(gold, pred)
    details = list(getattr(sc.score, "details", []))      # 다음 호출 때 덮어쓰이므로 바로 복사
    items = [{"level": lv, "name": n, "metric": m, "score": float(v), "n": cnt, "target": float(t),
              "pass": v >= t} for lv, n, m, v, cnt, t in rows]
    return {"items": items, "weighted": _weighted(items),
            "must_pass": all(i["pass"] for i in items if i["level"] == "필수"), "details": details}


def _top_key(path: str) -> str:
    """미검수 경로의 최상위 키. 'msds[0].hazard.h_statements[...]' → 'hazard', 'doc.page_count' → 'doc'."""
    p = re.sub(r"^msds\[\d+\]\.", "", path)
    return re.split(r"[.\[]", p, maxsplit=1)[0]


def unreviewed_items(doc_id: str, item_names: list[str]) -> dict[str, int]:
    """미검수 칸이 들어간 채점 항목과 그 칸 수 (D-35). 미검수 기록이 없으면 빈 dict."""
    p = paths.gold_unreviewed_path(doc_id)
    if not p.exists():
        return {}
    cnt = Counter(_top_key(x) for x in json.loads(p.read_text(encoding="utf-8")) if x)
    out: dict[str, int] = {}
    for top, k in cnt.items():
        for prefix in TOP_TO_ITEMS.get(top, []):
            for name in item_names:
                if name.startswith(prefix):
                    out[name] = out.get(name, 0) + k
    return out


def score_set(pairs: list[tuple[str, dict, dict]]) -> dict:
    """여러 문서 채점. pairs = [(문서번호, 골드, 결과)].

    항목별 점수는 문서 평균(TO21 채점기 설명과 같다). 평균 점수로 가중 종합 점수와 합격 판정을 다시 낸다.
    """
    if not pairs:
        raise ValueError("채점할 문서가 없습니다. 결과 폴더와 정답(data/gold/)을 확인하세요.")
    docs: dict[str, dict] = {}
    acc: dict[str, list[dict]] = defaultdict(list)
    meta: dict[str, tuple] = {}
    kinds: dict[str, Counter] = defaultdict(Counter)
    ref: dict[str, list[str]] = defaultdict(list)        # 항목 → 미검수 칸이 있는 문서
    details: list[dict] = []
    for doc_id, gold, pred in pairs:
        r = score_pair(gold, pred)
        failed = [i["name"] for i in r["items"] if i["level"] == "필수" and not i["pass"]]
        docs[doc_id] = {"weighted": r["weighted"], "must_pass": r["must_pass"], "failed_must": failed,
                        "passed": r["must_pass"] and r["weighted"] >= PASS_SCORE}
        for i in r["items"]:
            acc[i["name"]].append(i)
            meta[i["name"]] = (i["level"], i["metric"], i["target"])
        for name, kind, content in r["details"]:
            label = KIND.get(kind, kind)
            kinds[name][label] += 1
            details.append({"doc_id": doc_id, "item": name, "kind": label, "content": str(content)})
        for name in unreviewed_items(doc_id, [i["name"] for i in r["items"]]):
            ref[name].append(doc_id)

    items = []
    for name, lst in acc.items():
        lv, metric, target = meta[name]
        s = sum(x["score"] for x in lst) / len(lst)
        items.append({"level": lv, "name": name, "metric": metric, "score": s, "target": target,
                      "pass": s >= target, "n": sum(x["n"] for x in lst),
                      "docs_failed": sum(1 for x in lst if not x["pass"]),
                      "ref": bool(ref.get(name)), "ref_docs": ref.get(name, []),
                      **{k: kinds[name].get(k, 0) for k in KINDS}})
    items.sort(key=lambda i: LEVEL_ORDER[i["level"]])
    weighted = _weighted(items)
    must = [i for i in items if i["level"] == "필수"]
    must_pass = all(i["pass"] for i in must)
    return {"docs": docs, "items": items, "weighted": weighted,
            "must_pass": must_pass, "must_passed_count": sum(i["pass"] for i in must), "must_total": len(must),
            "passed": must_pass and weighted >= PASS_SCORE, "details": details}


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def write_report(result: dict, out_dir: Path, title: str) -> Path:
    """성적표를 파일로 저장하고 report.md 경로를 돌려준다.

    report.md   사람이 읽는 성적표 (요약, 항목 표, 문서별 점수)
    items.csv   항목별 점수·목표·통과·빠뜨림·지어냄·틀림·참고 표시
    docs.csv    문서별 가중 종합 점수, 필수 통과, 미달 필수 항목
    details.csv 필수 항목의 오류 상세 (보고 자료의 '자주 틀린 칸' 근거)
    result.json 결과 전체 (scripts/compare_scores.py가 읽는다)
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    item_cols = ["level", "name", "metric", "score", "target", "pass", "n", "docs_failed",
                 "빠뜨림", "지어냄", "틀림", "ref"]
    with open(out_dir / "items.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=item_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(result["items"])
    with open(out_dir / "docs.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "weighted", "must_pass", "passed", "failed_must"])
        for d, v in result["docs"].items():
            w.writerow([d, f"{v['weighted']:.1f}", v["must_pass"], v["passed"], "; ".join(v["failed_must"])])
    with open(out_dir / "details.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["doc_id", "item", "kind", "content"])
        w.writeheader()
        w.writerows(result.get("details", []))
    (out_dir / "result.json").write_text(json.dumps({"title": title, **result}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")

    n_docs = len(result["docs"])
    lines = [
        f"# 성적표: {title}", "",
        f"- 문서 {n_docs}건: {', '.join(result['docs'])}",
        f"- 가중 종합 점수 **{result['weighted']:.1f}점** (목표 {PASS_SCORE:.0f}점, 필수×3·중요×2·일반×1)",
        f"- 필수 항목 **{result['must_passed_count']}/{result['must_total']} 통과**",
        f"- 판정: **{'합격' if result['passed'] else '불합격'}** (필수 모두 목표 이상 + 종합 {PASS_SCORE:.0f}점 이상)",
        "",
        "## 항목별 점수 (문서 평균)", "",
        "| 중요도 | 항목 | 지표 | 점수 | 목표 | 판정 | 미달 문서 | 빠뜨림 | 지어냄 | 틀림 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i in result["items"]:
        mark = " (참고: 미검수 포함)" if i.get("ref") else ""
        lines.append(f"| {i['level']} | {i['name']}{mark} | {i['metric']} | {_pct(i['score'])} | {_pct(i['target'])} | "
                     f"{'통과' if i['pass'] else '미달'} | {i['docs_failed']}/{n_docs} | "
                     f"{i['빠뜨림']} | {i['지어냄']} | {i['틀림']} |")
    lines += [
        "",
        "- 빠뜨림·지어냄·틀림은 TO21 채점기가 **필수 항목**에 대해 남긴 상세(누락·오추출·불일치)를 센 것이다. 중요·일반 항목은 세지 않는다.",
        "- 목록 항목(성분, H·P코드, 규제 행 등)의 값이 틀리면 채점기는 '누락 1 + 오추출 1'로 센다. 빠뜨림·지어냄 수에 틀린 값이 섞여 있을 수 있다.",
    ]
    if any(i.get("ref") for i in result["items"]):
        lines.append("- '참고: 미검수 포함' 항목은 정답 일부가 검수 전 실버 값이다(D-35). 점수를 확정값으로 보고하지 않는다.")
    lines += ["", "## 문서별", "", "| 문서 | 가중 종합 | 필수 통과 | 미달 필수 항목 |", "|---|---|---|---|"]
    for d, v in result["docs"].items():
        lines.append(f"| {d} | {v['weighted']:.1f} | {'예' if v['must_pass'] else '아니오'} | "
                     f"{', '.join(v['failed_must']) or '-'} |")
    out = out_dir / "report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
