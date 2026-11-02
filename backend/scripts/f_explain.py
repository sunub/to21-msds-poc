"""추출 JSON → 정합성 검증 → 일치가 아닌 줄에 설명을 붙인다(11/02 F 결정 13, 설계서 13·40·44장).

    cd backend
    python scripts/f_explain.py ../data/silver/claude/T21-025.json             문장틀 설명만(LLM 없음), 샘플 CSV
    python scripts/f_explain.py ../data/silver/claude/T21-025.json --db --model qwen3_30b_a3b_rngd
                                                                              configs/models.yaml 의 모델로 LLM 설명
    python scripts/f_explain.py ../data/silver/claude --db --model qwen3_30b_a3b_rngd --out ../local/explain_db1
    --limit N   LLM 설명은 처음 N줄만(나머지는 문장틀). 서버를 처음 붙여 볼 때 쓴다

LLM 주소·키는 .env 에서 읽는다(models.yaml 의 base_url_env·api_key_env). 외부 중계 모델(gpt·claude 태그)은 쓸 수 없다.
요청에 HTODB 값이 들어가기 때문이다(D-47). 같은 이유로 --out 은 저장소 밖(local/ 등)에 둔다.
"""
import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND / "src") not in sys.path:
    sys.path.insert(0, str(BACKEND / "src"))

from msds.compliance.consistency import run_consistency  # noqa: E402
from msds.compliance.explain import ChatExplainer, explain_consistency  # noqa: E402
from msds.compliance.htodb.csv_repo import CsvRepo  # noqa: E402


def _files(paths):
    for p in map(Path, paths):
        for f in (sorted(p.glob("*.json")) if p.is_dir() else [p]):
            if not f.name.endswith(".review.json"):
                yield f


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="추출 JSON 파일 또는 폴더")
    ap.add_argument("--db", action="store_true", help="실제 HTODB(로컬 PostgreSQL). 없으면 샘플 CSV")
    ap.add_argument("--model", help="configs/models.yaml 모델 태그. 없으면 문장틀 설명만")
    ap.add_argument("--limit", type=int, help="LLM 설명을 붙일 최대 줄 수")
    ap.add_argument("--out", help="건마다 결과 JSON 을 쓸 폴더(저장소 밖)")
    a = ap.parse_args()
    repo = None if a.db else CsvRepo()
    llm = ChatExplainer(a.model) if a.model else None
    if llm is not None:  # 서버가 없으면 줄마다 재시도하며 오래 기다리지 않게 먼저 확인한다
        ok, msg = llm.ping()
        print(msg)
        if not ok:
            sys.exit(2)
    out_dir = Path(a.out) if a.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    total, problems, budget, t0 = Counter(), Counter(), a.limit, time.time()
    for path in _files(a.paths):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or "msds" not in doc:
            continue
        for i, item in enumerate(doc.get("msds") or []):
            res = run_consistency(doc, repo, i)
            todo = [f["id"] for f in res["consistency"]["findings"] if f["verdict"] != "일치"]
            ids = None if budget is None else set(todo[:max(budget, 0)])
            if llm is not None:
                total.update(explain_consistency(res, item, llm, ids=ids))
                budget = None if budget is None else budget - len(ids)
            total.update(explain_consistency(res, item))       # 남은 줄은 문장틀
            tag = path.stem + (f"#{i}" if len(doc["msds"]) > 1 else "")
            for f in res["consistency"]["findings"]:
                e = f.get("explanation")
                if not e:
                    continue
                mark = "검사O" if e["checked"] else "검사X"
                retry = f"  (다시 요청: {'; '.join(e['llm_problems'])[:80]})" if e["llm_problems"] else ""
                print(f"{tag} {f['id']} [{e['by']} {mark}] {e['summary']}{retry}")
                problems.update(re.sub(r"\s*[(:].*$|\s+\S+$", "", p) or p for p in e["llm_problems"])  # 값을 뗀 문제 종류
            if out_dir:
                (out_dir / f"{tag.replace('#', '_')}.explained.json").write_text(
                    json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"합계  설명 {total['설명']}  LLM {total['llm']}  문장틀 {total['template']}  검사 통과 {total['검사 통과']}  "
          f"LLM 실패→문장틀 {total['대체']}  ({time.time() - t0:.0f}초)")
    if problems:
        print("LLM 검사 문제: " + ", ".join(f"{k} {v}" for k, v in problems.most_common(6)))
    print(f"지식: {'실제 HTODB' if a.db else '샘플 CSV(to21_sample)'} · 설명: {a.model or '문장틀만'}")


if __name__ == "__main__":
    main()
