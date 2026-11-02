"""추출 JSON → 2차 정합성 검증(2항·15항) 결과를 한눈에 보거나 파일로 남긴다.

    cd backend
    python scripts/f_consistency.py ../data/silver/claude/T21-025.json          한 건 (샘플 CSV)
    python scripts/f_consistency.py ../data/silver/claude --db                   폴더 전체, 실제 HTODB
    python scripts/f_consistency.py ../data/silver/claude --db --out ../local/consistency
                                                                                  건마다 결과 JSON 저장
    --all   불일치·경계·근거부족만이 아니라 일치 줄도 모두 출력

결과 JSON 은 설계서 44장 consistency 블록이다. 실제 HTODB 값이 들어가므로 --out 은 저장소 밖(local/ 등)에 둔다(D-47).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND / "src") not in sys.path:
    sys.path.insert(0, str(BACKEND / "src"))

from msds.compliance.consistency import run_consistency  # noqa: E402
from msds.compliance.htodb.csv_repo import CsvRepo  # noqa: E402

KEYS = ("일치", "불일치", "경계", "근거부족")


def _files(paths):
    """추출 JSON 만. 같은 폴더의 *.review.json(추출 검수 기록)은 건너뛴다."""
    for p in map(Path, paths):
        for f in (sorted(p.glob("*.json")) if p.is_dir() else [p]):
            if not f.name.endswith(".review.json"):
                yield f


def _line(f):
    if f["section"] == "2":
        what = f"{f['class_code']}{'(' + f['form'] + ')' if f.get('form') else ''}  MSDS {f.get('msds_value')} / 우리 " \
               f"{(f.get('our_value') or {}).get('low')}~{(f.get('our_value') or {}).get('high')}"
    else:
        what = f"성분{f['comp_ref']} {f['item_code']}  MSDS {f.get('msds_value')} / 기대 {f.get('expected')}"
    kind = f" [{f['type']}·{f['severity']}]" if f.get("type") else ""
    return f"    {f['id']} {f['verdict']}{kind}  {what}  — {f['reason'][:120]}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="추출 JSON 파일 또는 폴더")
    ap.add_argument("--db", action="store_true", help="실제 HTODB(로컬 PostgreSQL) 사용. 없으면 샘플 CSV")
    ap.add_argument("--out", help="건마다 결과 JSON 을 쓸 폴더(저장소 밖)")
    ap.add_argument("--all", action="store_true", help="일치 줄도 출력")
    a = ap.parse_args()
    repo = None if a.db else CsvRepo()
    out_dir = Path(a.out) if a.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    total = Counter()
    for path in _files(a.paths):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or "msds" not in doc:
            print(f"{path.name}: 추출 JSON 이 아니라 건너뜀")
            continue
        for i in range(len(doc.get("msds") or [{}])):
            res = run_consistency(doc, repo, i)
            c = res["consistency"]
            s = c["summary"]
            tag = path.stem + (f"#{i}" if len(doc.get("msds") or []) > 1 else "")
            print(f"{tag}  {c['product_type']['value']}  "
                  + "  ".join(f"{sec} " + "/".join(f"{k}{s[sec][k]}" for k in KEYS) for sec in ("2항", "15항"))
                  + f"  심각도 높음{s['전체']['심각도']['높음']}  참고{s['참고']}")
            for f in c["findings"]:
                if a.all or f["verdict"] != "일치":
                    print(_line(f))
            total.update({k: s["전체"][k] for k in KEYS})
            total.update({f"심각도 {k}": v for k, v in s["전체"]["심각도"].items()})
            if out_dir:
                (out_dir / f"{tag.replace('#', '_')}.consistency.json").write_text(
                    json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("합계  " + "  ".join(f"{k} {total[k]}" for k in (*KEYS, "심각도 높음", "심각도 중간", "심각도 낮음")))
    print(f"지식: {'실제 HTODB' if a.db else '샘플 CSV(to21_sample)'}")


if __name__ == "__main__":
    main()
