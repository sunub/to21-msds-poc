"""전처리 실행 (역할 C, D-44): data/raw/의 원본 PDF → data/pages/<문서번호>/

사용법
  python scripts/preprocess.py --purpose 개발          # 개발용 10건
  python scripts/preprocess.py --docs T21-S016 T21-025
  python scripts/preprocess.py --all --force            # 전부 다시

결과를 manifest와 비교해 다른 점을 보여 준다. manifest는 사람이 확인한 기준표이므로
자동으로 고치지 않는다. 판별이 맞으면 --update-manifest로 반영한다.
"""
import argparse

import _common  # noqa: F401
from msds.common import manifest
from msds.preprocess.render import preprocess

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", nargs="*")
    ap.add_argument("--purpose", choices=manifest.PURPOSES)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true", help="이미 만든 결과도 다시 만든다")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--update-manifest", action="store_true")
    a = ap.parse_args()
    if not (a.docs or a.purpose or a.all):
        ap.error("--docs, --purpose, --all 중 하나를 고르세요")

    rows = manifest.load()
    targets = manifest.select(a.purpose, a.docs) if not a.all else rows
    changed = False
    for r in targets:
        try:
            pdf = manifest.raw_pdf(r)
        except FileNotFoundError as e:
            print(f"[없음] {e}")
            continue
        m = preprocess(pdf, r["doc_id"], dpi=a.dpi, force=a.force)
        diff = [f"{k}: manifest={r.get(k) or '-'} / 판별={m.get(k) or '-'}"
                for k in ("text_layer", "language", "input_mode")
                if m.get(k) is not None and (r.get(k) or None) != m.get(k)]   # 판별하지 못한 값(None)은 비교하지 않는다
        flag = "확인 필요 → " + "; ".join(diff) if diff else "manifest와 같음"
        print(f"[완료] {r['doc_id']} {m['page_count']}쪽 {m['text_layer']} {m['input_mode']} | {flag}")
        if a.update_manifest and diff:
            for row in rows:
                if row["doc_id"] == r["doc_id"]:
                    row.update({k: m.get(k) or row.get(k) for k in ("text_layer", "language", "input_mode")})
                    row["pages"] = m["page_count"]
                    changed = True
    if changed:
        manifest.save(rows)
        print("manifest를 고쳤습니다. 커밋 전에 확인하세요.")
