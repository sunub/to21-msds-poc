"""깨진 텍스트층 OCR (역할 C, 시험 단계): data/raw/의 원본 PDF → data/pages/<문서번호>/p001.ocr.*

사용법 (전처리를 먼저 돌린다. PaddleOCR이 설치된 환경에서)
  python scripts/ocr_pages.py --docs T21-S003              # 텍스트층이 '정상'이 아닌 쪽만
  python scripts/ocr_pages.py --docs T21-S003 --pages 1 3  # 지정한 쪽만
  python scripts/ocr_pages.py --docs T21-S003 --cells-only # OCR은 두고 칸(p001.ocr.cells.json)만 다시 만든다

모델 입력(p001.txt)은 바꾸지 않는다. 자세한 내용은 src/msds/preprocess/ocr.py 머리말.
"""
import argparse

import _common  # noqa: F401
from msds.common import manifest
from msds.preprocess.ocr import ocr_document, rebuild_cells

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", nargs="+", required=True)
    ap.add_argument("--pages", nargs="*", type=int, help="OCR할 쪽 (없으면 텍스트층이 '정상'이 아닌 쪽)")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--cells-only", action="store_true", help="OCR을 다시 돌리지 않고 칸만 다시 만든다")
    a = ap.parse_args()

    for r in manifest.select(None, a.docs):
        if a.cells_only:
            for c in rebuild_cells(r["doc_id"]):
                kinds = {}
                for cell in c["cells"]:
                    kinds[cell["kind"]] = kinds.get(cell["kind"], 0) + 1
                print(f"[칸] {r['doc_id']} {c['page']}쪽 값 열 x={c['value_x']} {kinds} 뺀 조각 {len(c['dropped'])}")
            continue
        try:
            pdf = manifest.raw_pdf(r)
        except FileNotFoundError as e:
            print(f"[없음] {e}")
            continue
        for s in ocr_document(pdf, r["doc_id"], pages=a.pages or None, dpi=a.dpi):
            print(f"[완료] {r['doc_id']} {s['page']}쪽 {s['lines']}줄 평균 신뢰도 {s['mean_score']} "
                  f"(0.8 미만 {s['low_score_lines']}줄)")
