"""오류 주입 평가: 25번 황산 추출본을 한 곳씩 일부러 틀리게 바꾸고, 엔진이 그 틀림을 기대한 판정으로 잡는지 본다.

근거: 설계서 48장 e2e "오류 주입: 25번 2항에서 피부 부식성 삭제, 15항 사고대비물질 삭제 → 과소분류(높음), 누락(높음) 탐지",
49장 평가 데이터 ② 오류 주입셋("정답 MSDS의 2·15항을 일부러 바꾼 사본"), 지표 "과소분류·누락 탐지율 ≥ 95%".
설계서의 두 경우(INJ-01, INJ-02)에 판정 유형마다 한 경우 이상을 더했다(11/02 F). INJ-05는 이미 있는 형태 표기 차이를
고쳐 넣는 대조군이다(고치면 불일치가 사라져야 한다).
cause 는 그 줄에 붙어야 할 차이 원인 코드다(설계서 41장, trace.CAUSE_TEXT). 설명 단계가 읽을 근거가 맞게 붙는지 함께 본다(11/02 F).

    cd backend
    python scripts/f_inject.py                 샘플 CSV(to21_sample)
    python scripts/f_inject.py --db            실제 HTODB
    python scripts/f_inject.py --md ..\\docs\\2026-11-02_F_오류주입_결과.md   결과표를 마크다운으로 저장
"""
import argparse
import copy
import json
import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND / "src") not in sys.path:
    sys.path.insert(0, str(BACKEND / "src"))

from msds.compliance.consistency import run_consistency  # noqa: E402
from msds.compliance.htodb.csv_repo import CsvRepo  # noqa: E402

INPUT = ROOT / "data" / "silver" / "claude" / "T21-025.json"


# ── 바꾸는 손 ──────────────────────────────────────────────────────
def drop_class(cc):
    def f(m):
        m["hazard"]["classes"] = [c for c in m["hazard"]["classes"] if c["class_code"] != cc]
    return f


def set_class(cc, **kw):
    def f(m):
        for c in m["hazard"]["classes"]:
            if c["class_code"] == cc:
                c.update(kw)
    return f


def add_class(cc, category, route_form=None):
    def f(m):
        m["hazard"]["classes"].append({"seq": 99, "group": "건강", "class_code": cc, "category": category,
                                       "route_form": route_form, "effect": None, "target_organs": [], "raw": "주입"})
    return f


def drop_reg(comp_ref, item):
    def f(m):
        m["regulations"] = [r for r in m["regulations"] if not (str(r["comp_ref"]) == comp_ref and r["item_code"] == item)]
    return f


def set_reg(comp_ref, item, **kw):
    def f(m):
        for r in m["regulations"]:
            if str(r["comp_ref"]) == comp_ref and r["item_code"] == item:
                r.update(kw)
    return f


def set_flash_point(value):
    def f(m):
        for p in m["physchem"]:
            if p["prop_code"] == "FLASH_POINT":
                p["q"] = {**(p.get("q") or {}), "value": value, "status": "값있음", "unit": "℃"}
    return f


def set_signal(word):
    def f(m):
        m["hazard"]["signal_word"] = word
    return f


def drop_pictogram(code):
    def f(m):
        m["hazard"]["pictograms"] = [p for p in m["hazard"]["pictograms"] if p.get("code") != code]
    return f


def pct(v):
    return {"raw": f"{v}% 이상", "value": None, "lower_op": ">=", "lower": v, "upper_op": None, "upper": None, "unit": "%"}


# ── 주입 목록 ── key: 2항은 (class_code, form), 15항은 (comp_ref, item_code) ─────────────
CASES = [
    {"id": "INJ-01", "cause": "CAT_LOWER", "design": True, "what": "2항 피부 부식성 구분1 삭제", "section": "2", "key": ("HH_SKIN_CORR", None),
     "expect": ("불일치", "과소분류", "높음"), "mutate": [drop_class("HH_SKIN_CORR")]},
    {"id": "INJ-02", "cause": "REG_MISSING", "design": True, "what": "15항 황산 사고대비물질 행 삭제", "section": "15", "key": ("1", "CCA_ACCIDENT"),
     "expect": ("불일치", "규제 누락", "높음"), "mutate": [drop_reg("1", "CCA_ACCIDENT")]},
    {"id": "INJ-03", "cause": "CAT_LOWER", "what": "2항 눈 손상 구분1 → 2 (낮춤)", "section": "2", "key": ("HH_EYE_DMG", None),
     "expect": ("불일치", "과소분류", "높음"), "mutate": [set_class("HH_EYE_DMG", category="2")]},
    {"id": "INJ-04", "cause": "CAT_HIGHER", "what": "2항 급성독성(경구) 구분3 추가 (근거 없는 분류)", "section": "2", "key": ("HH_ACUTE_ORAL", None),
     "expect": ("불일치", "과대분류", "낮음"), "mutate": [add_class("HH_ACUTE_ORAL", "3")]},
    {"id": "INJ-05", "control": True, "what": "대조군: 흡입 형태 '증기' → '분진·미스트'(우리 결과와 같게 고침)", "section": "2",
     "key": ("HH_ACUTE_INHAL", "분진·미스트"), "expect": ("일치", None, None),
     "mutate": [set_class("HH_ACUTE_INHAL", route_form="분진·미스트")]},
    {"id": "INJ-06", "cause": "THRESHOLD_DIFF", "what": "15항 작업환경측정 기준 '1% 이상' → '10% 이상'", "section": "15", "key": ("1", "OSH_MEASURE"),
     "expect": ("불일치", "기준 불일치", "중간"), "mutate": [set_reg("1", "OSH_MEASURE", threshold=pct(10))]},
    {"id": "INJ-07", "cause": "OVER_STATED", "what": "15항 물 유독물질 '비해당' → '해당' (근거 없는 기재)", "section": "15", "key": ("2", "CCA_TOXIC"),
     "expect": ("불일치", "과기재", "낮음"), "mutate": [set_reg("2", "CCA_TOXIC", applicable="해당")]},
    {"id": "INJ-08", "cause": "REG_MISSING", "what": "15항 황산 PSM '해당' → '비해당'", "section": "15", "key": ("1", "OSH_PSM"),
     "expect": ("불일치", "규제 누락", "높음"), "mutate": [set_reg("1", "OSH_PSM", applicable="비해당", threshold=None)]},
    {"id": "INJ-09", "cause": "REG_MISSING", "what": "9항 인화점 '해당없음' → 15℃ (위험물 비해당 기재는 그대로)", "section": "15", "key": ("MIX", "DG_HAZMAT"),
     "expect": ("불일치", "규제 누락", "높음"), "mutate": [set_flash_point(15)]},
    {"id": "INJ-10", "cause": "LABEL_DIFF", "what": "2항 신호어 '위험' → '경고'", "section": "2", "key": ("LABEL_SIGNAL_WORD", None),
     "expect": ("불일치", "표시 요소 불일치", "중간"), "mutate": [set_signal("경고")]},
    {"id": "INJ-11", "cause": "LABEL_MISSING", "what": "2항 그림문자 GHS06(해골) 삭제", "section": "2", "key": ("LABEL_PICTOGRAMS", None),
     "expect": ("불일치", "표시 요소 불일치", "중간"), "mutate": [drop_pictogram("GHS06")]},
]


def _key(f):
    return (f.get("class_code"), f.get("form")) if f["section"] == "2" else (str(f.get("comp_ref")), f.get("item_code"))


def _findings(doc, repo):
    c = run_consistency(doc, repo)["consistency"]
    return {(f["section"], *_key(f)): f for f in c["findings"]}


def _label(f):
    return f["verdict"] + (f"·{f['type']}" if f.get("type") else "")


def run_case(base_doc, case, repo, base=None):
    doc = copy.deepcopy(base_doc)
    for fn in case["mutate"]:
        fn(doc["msds"][0])
    base = base if base is not None else _findings(base_doc, repo)
    now = _findings(doc, repo)
    k = (case["section"], *case["key"])
    got = now.get(k)
    ok = got is not None and (got["verdict"], got.get("type"), got.get("severity")) == case["expect"]
    codes = [c["code"] for c in (got or {}).get("causes") or []]
    cause_ok = (case.get("cause") in codes) if case.get("cause") else (got is not None and not codes)
    side = []
    for key in sorted(set(base) | set(now), key=str):
        if key == k:
            continue
        a, b = base.get(key), now.get(key)
        if (a and _label(a)) != (b and _label(b)):
            side.append(f"{key[0]}항 {'/'.join(str(x) for x in key[1:] if x)}: {a and _label(a) or '없음'} → {b and _label(b) or '없음'}")
    before = base.get(k)
    return {"id": case["id"], "what": case["what"], "design": case.get("design", False), "control": case.get("control", False),
            "expect": case["expect"], "before": before and _label(before), "got": got and _label(got),
            "got_severity": got and got.get("severity"), "detected": ok, "reason": got and got.get("reason"), "side": side,
            "cause": case.get("cause"), "causes": codes, "cause_ok": cause_ok}


def evaluate(repo=None, doc=None):
    doc = doc or json.loads(INPUT.read_text(encoding="utf-8"))
    base = _findings(doc, repo)
    results = [run_case(doc, c, repo, base) for c in CASES]
    tests = [r for r in results if not r["control"]]
    high = [r for r in tests if r["expect"][2] == "높음"]
    summary = {"cases": len(tests), "detected": sum(r["detected"] for r in tests),
               "high_cases": len(high), "high_detected": sum(r["detected"] for r in high),
               "controls_ok": all(r["detected"] for r in results if r["control"]),
               "cause_ok": sum(r["cause_ok"] for r in results), "cause_cases": len(results),
               "with_side_effects": sum(1 for r in results if r["side"])}
    return {"summary": summary, "results": results}


def to_markdown(out, source):
    s = out["summary"]
    lines = [
        "# 오류 주입 평가 결과 (25번 황산)", "",
        f"- 실행일: {date.today().isoformat()} · 지식: {source} · 도구: `backend/scripts/f_inject.py`",
        "- 근거: 설계서 48장(e2e 오류 주입), 49장(평가 데이터 ② 오류 주입셋, 과소분류·누락 탐지율 목표 ≥ 95%)",
        "- 방법: 25번 추출본을 복사해 한 곳만 바꾼 뒤 엔진을 다시 돌려, 바꾼 자리에서 기대한 판정·유형·심각도가 나오는지 본다.",
        "",
        f"**탐지율 {s['detected']}/{s['cases']}** · 높음(과소분류·규제 누락) {s['high_detected']}/{s['high_cases']} · "
        f"대조군 {'통과' if s['controls_ok'] else '실패'} · 차이 원인 코드 {s['cause_ok']}/{s['cause_cases']}",
        "",
        "| ID | 바꾼 것 | 기대 | 바꾸기 전 → 후 | 탐지 | 원인 코드(기대) | 같이 바뀐 줄 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in out["results"]:
        exp = r["expect"][0] + (f"·{r['expect'][1]}·{r['expect'][2]}" if r["expect"][1] else "")
        tag = " (설계서)" if r["design"] else " (대조군)" if r["control"] else ""
        lines.append(f"| {r['id']}{tag} | {r['what']} | {exp} | {r['before'] or '없음'} → {r['got'] or '없음'} | "
                     f"{'O' if r['detected'] else 'X'} | {'·'.join(r['causes']) or '-'} ({r['cause'] or '없음'}) "
                     f"{'O' if r['cause_ok'] else 'X'} | {'<br>'.join(r['side']) or '-'} |")
    lines += ["", "같이 바뀐 줄은 한 곳을 바꾸면 따라서 맞지 않게 되는 다른 칸이다. 예를 들어 피부 부식성을 지우면 "
              "MSDS에 남은 H314가 분류와 맞지 않아 표시 요소 줄도 함께 잡힌다.", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", action="store_true", help="실제 HTODB 사용")
    ap.add_argument("--md", help="결과표를 저장할 마크다운 경로")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    repo = None if a.db else CsvRepo()
    source = "실제 HTODB" if a.db else "샘플 CSV(to21_sample)"
    out = evaluate(repo)
    for r in out["results"]:
        print(f"{r['id']} {'O' if r['detected'] else 'X'}  {r['what']}  →  {r['got']}  (기대 {r['expect'][0]}"
              f"{'·' + r['expect'][1] if r['expect'][1] else ''})  원인 {'·'.join(r['causes']) or '-'}"
              f" {'O' if r['cause_ok'] else 'X'}")
        for s in r["side"]:
            print(f"      같이 바뀐 줄: {s}")
    s = out["summary"]
    print(f"탐지율 {s['detected']}/{s['cases']} · 높음 {s['high_detected']}/{s['high_cases']} · 대조군 "
          f"{'통과' if s['controls_ok'] else '실패'} · 원인 코드 {s['cause_ok']}/{s['cause_cases']} · 지식 {source}")
    if a.md:
        Path(a.md).write_text(to_markdown(out, source), encoding="utf-8")
        print(f"저장: {a.md}")
    sys.exit(0 if s["detected"] == s["cases"] and s["controls_ok"] else 1)


if __name__ == "__main__":
    main()
