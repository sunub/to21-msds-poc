"""검수표 → 골드 (역할 A, D-36). 사용법: python scripts/build_gold.py --docs T21-S016 ..."""
import argparse

import _common  # noqa: F401
from msds.common import manifest
from msds.review.build_gold import build_gold_file

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", nargs="*")
    ap.add_argument("--purpose", choices=manifest.PURPOSES)
    a = ap.parse_args()
    for r in manifest.select(a.purpose, a.docs):
        print(build_gold_file(r["doc_id"]))
