"""25번 황산 e2e 정답본(2항): 판정 목록을 만들고 고정본과 비교하거나 다시 쓴다.

근거: 설계서 47장(7단계 완료 기준 "25번 e2e 결과 고정"), 48장(e2e 케이스), 10/30 결정 B2(설계서 38~42장 기대 결과 기준).
고정본은 우리 실제 결과다. 설계서 38장(화면 예시, 가상 판정)과 다른 줄은 줄마다 이유를 함께 적는다.

    cd backend
    python scripts/f_e2e_25.py            지금 결과와 고정본의 차이를 보여 줌
    python scripts/f_e2e_25.py --write    지금 결과로 고정본을 다시 씀 (결과가 바뀐 이유를 작업 기록에 남길 것)
    python scripts/f_e2e_25.py --db       샘플 CSV 대신 실제 HTODB(로컬 PostgreSQL)로 실행
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND / "src") not in sys.path:
    sys.path.insert(0, str(BACKEND / "src"))

from msds.compliance.htodb.csv_repo import CsvRepo  # noqa: E402
from msds.compliance.mixture.build_components import build_components  # noqa: E402
from msds.compliance.mixture.class_lookup_db import make_db_class_lookup, make_db_tox_lookup  # noqa: E402
from msds.compliance.mixture.classify_mixture import classify_mixture_all  # noqa: E402
from msds.compliance.mixture.physical import physical_inputs  # noqa: E402
from msds.compliance.mixture.rules_loader import load_mixture_rules  # noqa: E402
from msds.compliance.mixture.verdict import aggregate_verdicts  # noqa: E402

INPUT = ROOT / "data" / "silver" / "claude" / "T21-025.json"
FIXED = BACKEND / "tests" / "e2e" / "T21-025_2항_기대.json"
KNOWLEDGE = "htodb-94f8b6ff7f24"  # 샘플 CSV와 같음을 test_F_htodb_csv 대조 시험으로 확인한 적재본
COMPARED = ("msds_form", "msds_value", "our_value", "verdict", "type", "severity", "rule_id")
ATE_DIGITS = {("HH_ACUTE_ORAL", None): 1, ("HH_ACUTE_INHAL", "분진·미스트"): 3}  # 설계서 24장 자릿수

# 설계서 38장 화면 예시(25번 황산, 가상 판정)의 2항 9줄. 표시 요소 줄(H318 경고)은 C3 결정으로 쓰지 않는다.
DESIGN_38 = {
    ("HH_ACUTE_INHAL", "분진·미스트"): ("구분2 (증기)", "구분2 (분진·미스트)", "불일치", "중간"),
    ("PH_METAL_CORR", None): ("구분1", "— (제품 시험자료 없음)", "근거부족", None),
    ("ENV_AQ_CHRONIC", None): ("구분3", "— (기준정보 없음)", "근거부족", None),
    ("HH_ACUTE_ORAL", None): ("미기재", "분류안됨 (ATEmix > 2,000)", "일치", None),
    ("HH_SKIN_CORR", None): ("구분1", "구분1", "일치", None),
    ("HH_EYE_DMG", None): ("구분1", "구분1", "일치", None),
    ("HH_CARCINOGEN", None): ("구분1A", "구분1A", "일치", None),
    ("HH_STOT_SE", None): ("구분1", "구분1", "일치", None),
}
DIFF_REASON = {
    ("PH_METAL_CORR", None): (
        "설계서 안에서 31장(다른 물리적 위험성은 시험자료가 없으면 근거부족)과 33장(D-17: UN 운송정보 → 대표성분 분류 → 9항)이 "
        "다르다. 33장(TO21 로직)을 따랐다. UN1830은 8급 용기등급 II라 운송 규칙(8급 III)에 걸리지 않고, "
        "대표성분 황산의 지식DB 분류가 금속부식성 1이라 일치."),
    ("ENV_AQ_CHRONIC", None): (
        "지식DB에 황산·물의 수생 분류 행이 없다(실제 HTODB로도 확인). 빈칸을 '분류안됨'으로 보는 현재 가정 때문에 "
        "MSDS 구분3이 과대분류(낮음)로 나온다. 빈칸을 '미검토'로 보면 38장처럼 근거부족이 된다. TO21 확인 요청: 빈칸의 뜻."),
    ("HH_STOT_SE", None): (
        "실제 HTODB(htodb-94f8b6ff7f24)에 황산의 특정표적장기(1회) 분류 행이 없다. 38장 화면은 가상 판정이다. "
        "빈칸을 '분류안됨'으로 보는 현재 가정 때문에 과대분류(낮음). TO21 확인 요청: 빈칸의 뜻, 황산 표적장기 분류 출처."),
}


def sha256(path: Path) -> str:
    """JSON 내용의 해시. 줄바꿈(CRLF/LF)·들여쓰기가 달라도 내용이 같으면 같은 값이다(Windows·Mac 공용)."""
    canon = json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _key(v):
    return f"{v['class_code']}|{v['form'] or ''}"


def _lookups(source):
    if source == "db":
        return make_db_class_lookup(), make_db_tox_lookup(), "HTODB 로컬 PostgreSQL"
    repo = CsvRepo()
    if not repo.available():
        raise FileNotFoundError(f"지식DB 샘플 CSV가 없음: {repo.folder}")
    return make_db_class_lookup(repo), make_db_tox_lookup(repo), "to21_sample CSV"


def run(source: str = "csv") -> dict:
    """25번 황산을 채점기에 넣어 비교에 쓰는 부분만 돌려준다. 같은 입력이면 항상 같은 값이어야 한다."""
    item = json.loads(INPUT.read_text(encoding="utf-8"))["msds"][0]
    class_lookup, tox_lookup, _ = _lookups(source)
    b = build_components(item, class_lookup, tox_lookup)
    results = classify_mixture_all(b["components"], b["mixture_props"], state=b["mixture_props"].get("STATE"),
                                   physical=physical_inputs(item))
    out = aggregate_verdicts(results, item["hazard"]["classes"])
    ate = {}
    for r in results:
        k = (r["class_code"], r.get("form"))
        if k in ATE_DIGITS:
            d = ATE_DIGITS[k]
            ate[f"{k[0]}|{k[1] or ''}"] = {"low": round(r["calc"]["ate_mix_low"], d), "high": round(r["calc"]["ate_mix_high"], d)}
    return {
        "verdicts": [{"class_code": v["class_code"], "form": v["form"], **{f: v[f] for f in COMPARED}} for v in out["verdicts"]],
        "excluded": [{"class_code": e["class_code"], "form": e["form"], "status": e["status"]} for e in out["excluded"]],
        "ate_mix": ate,
    }


def _design(v):
    d = DESIGN_38.get((v["class_code"], v["form"]))
    if d is None:
        return None
    msds, expected, verdict, severity = d
    same = v["verdict"] == verdict and (severity is None or v["severity"] == severity)
    return {"msds": msds, "expected": expected, "verdict": verdict, "severity": severity, "same": same}


def build_fixed(now: dict, source_name: str) -> dict:
    verdicts = []
    for v in now["verdicts"]:
        row = dict(v)
        d = _design(v)
        row["design_38"] = d
        if d and not d["same"]:
            row["diff_reason"] = DIFF_REASON.get((v["class_code"], v["form"]), "이유 미기재 — 확인 필요")
        verdicts.append(row)
    return {
        "meta": {
            "doc": "T21-025 황산 (혼합물: 황산 93~98%, 물 2~7%)",
            "scope": "2항 유해성 분류 판정 목록. 표시 요소·15항은 별도",
            "input": str(INPUT.relative_to(ROOT)).replace("\\", "/"),
            "input_sha256": sha256(INPUT),
            "rules_version": load_mixture_rules()["meta"]["version"],
            "knowledge": f"{source_name} (= {KNOWLEDGE}, 대조 시험으로 확인)",
            "fixed_on": date.today().isoformat(),
            "basis": "10/30 결정 B2: 설계서 38~42장 기대 결과 기준. 설계서와 다른 줄은 diff_reason 에 이유",
            "compared_fields": list(COMPARED),
        },
        "summary": dict(sorted(Counter(v["verdict"] for v in now["verdicts"]).items())),
        "verdicts": verdicts,
        "excluded": now["excluded"],
        "ate_mix": now["ate_mix"],
    }


def compare(fixed: dict, now: dict) -> list[str]:
    """고정본과 지금 결과의 차이를 사람이 읽는 문장 목록으로. 빈 목록이면 같다."""
    out = []
    a = {_key(v): v for v in fixed["verdicts"]}
    b = {_key(v): v for v in now["verdicts"]}
    for k in sorted(a.keys() - b.keys()):
        out.append(f"{k}: 고정본에만 있음")
    for k in sorted(b.keys() - a.keys()):
        out.append(f"{k}: 지금 결과에만 있음 → {b[k]['verdict']}")
    for k in sorted(a.keys() & b.keys()):
        for f in COMPARED:
            if a[k][f] != b[k][f]:
                out.append(f"{k}: {f} 고정본 {a[k][f]!r} → 지금 {b[k][f]!r}")
    ex = lambda rows: sorted((r["class_code"], r["form"] or "", r["status"]) for r in rows)
    if ex(fixed["excluded"]) != ex(now["excluded"]):
        out.append(f"비교 제외 항목이 다름: 고정본 {ex(fixed['excluded'])} → 지금 {ex(now['excluded'])}")
    if fixed["ate_mix"] != now["ate_mix"]:
        out.append(f"ATEmix 숫자가 다름: 고정본 {fixed['ate_mix']} → 지금 {now['ate_mix']}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="지금 결과로 고정본을 다시 씀")
    ap.add_argument("--db", action="store_true", help="실제 HTODB 사용")
    a = ap.parse_args()
    source = "db" if a.db else "csv"
    now = run(source)
    if a.write:
        FIXED.parent.mkdir(parents=True, exist_ok=True)
        fixed = build_fixed(now, _lookups(source)[2])
        FIXED.write_text(json.dumps(fixed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"고정본을 썼음: {FIXED.relative_to(ROOT)}  {fixed['summary']}")
        for v in fixed["verdicts"]:
            if v.get("diff_reason"):
                print(f"  설계서 38장과 다름: {_key(v)}  38장 {v['design_38']['verdict']} / 우리 {v['verdict']}")
        return
    if not FIXED.exists():
        print("고정본이 없음 → --write 로 만드세요")
        sys.exit(1)
    diffs = compare(json.loads(FIXED.read_text(encoding="utf-8")), now)
    print("고정본과 같음" if not diffs else "\n".join(["고정본과 다름:"] + [f"  {d}" for d in diffs]))
    sys.exit(1 if diffs else 0)


if __name__ == "__main__":
    main()
