"""검수표 만들기 (역할 A, D-36). 사용법: python scripts/make_review_sheet.py --docs T21-S016 ..."""
import argparse

import _common  # noqa: F401
from msds.common import manifest
from msds.review.make_sheet import make_review_sheet

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", nargs="*")
    ap.add_argument("--purpose", choices=manifest.PURPOSES)
    a = ap.parse_args()
    for r in manifest.select(a.purpose, a.docs):
        print(make_review_sheet(r["doc_id"]))
