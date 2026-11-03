"""같은 정합성 검증 요청을 여러 번(순차·동시) 보내 결과가 흔들리는지 본다(11/03 F).

    cd backend
    python scripts/f_stability.py ../data/silver/claude --db --repeat 3                        판정만(설명은 문장틀)
    python scripts/f_stability.py ../data/silver/claude --db --model qwen3_30b_a3b_rngd \\
        --repeat 3 --concurrency 8 --out ../local/stability                                   LLM 설명까지, 동시 요청 포함

회차: 순차 --repeat 회(1회차가 기준) → --concurrency 가 2 이상이면 같은 요청을 그 수만큼 동시에 보내는 회차 하나를 더 돈다.
흔들림을 세 층으로 나눠 센다. 모두 1회차와 비교한다.
  1. 판정(규칙 엔진): 판정·유형·심각도·우리 값·MSDS 값·원인 코드. 같아야 한다(기준 100%)
     지식DB 접속이 실패하면 엔진은 멈추지 않고 근거부족으로 남기므로, 동시 요청에서 판정이 바뀌면 먼저 DB 접속을 의심한다.
  2. 설명(LLM, temperature 0): 쓴 쪽(LLM·문장틀), 검사 통과, 글 속 숫자·코드·구분, 문장 전체
     temperature 0이어도 동시 요청이 한 묶음(batch)으로 계산되면 글이 조금 달라질 수 있다. 사실(숫자·코드·구분)이 같은지가 중요하다.
  3. 시스템: 예외, 줄당 LLM 시간(중앙값·95%), 회차 전체 시간

--out 에는 보고서(stability.md)와 달라진 줄 목록(diffs.json)을 쓴다. 결과에 지식DB 값이 들어가므로 저장소 밖(local/)에 둔다(D-47).
"""
import argparse
import copy
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND / "src") not in sys.path:
    sys.path.insert(0, str(BACKEND / "src"))

from msds.compliance.consistency import run_consistency  # noqa: E402
from msds.compliance.explain import _CATEGORY, _CODE, ChatExplainer, explain_consistency, text_numbers  # noqa: E402
from msds.compliance.htodb.csv_repo import CsvRepo  # noqa: E402


def _files(paths):
    for p in map(Path, paths):
        for f in (sorted(p.glob("*.json")) if p.is_dir() else [p]):
            if not f.name.endswith(".review.json"):
                yield f


def signature(f) -> dict:
    """판정 줄 하나에서 비교할 값. verdict 는 엔진 판정, expl 은 설명."""
    e = f.get("explanation") or {}
    text = " ".join([e.get("summary") or ""] + list(e.get("reasons") or []))
    facts = sorted(set(text_numbers(text)) | set(_CODE.findall(text)) | {f"구분 {c}" for c in _CATEGORY.findall(text)})
    return {
        "verdict": [f.get("verdict"), f.get("type"), f.get("severity"), f.get("our_value", f.get("expected")),
                    f.get("msds_value"), [c["code"] for c in f.get("causes") or []]],
        "by": e.get("by"), "checked": e.get("checked"), "facts": facts, "text": text if e else None,
        "seconds": e.get("seconds"),
    }


def run_job(doc, i, repo, llm):
    t0 = time.time()
    doc = copy.deepcopy(doc)  # 동시 요청이 같은 입력 객체를 함께 건드리지 않게
    try:
        res = run_consistency(doc, repo, i)
        item = doc["msds"][i]
        if llm is not None:
            explain_consistency(res, item, llm)
        explain_consistency(res, item)  # LLM 이 없거나 실패한 줄은 문장틀
        return {f["id"]: signature(f) for f in res["consistency"]["findings"]}, None, time.time() - t0
    except Exception as e:  # 한 요청이 실패해도 다른 요청은 계속 본다
        return None, f"{type(e).__name__}: {e}"[:200], time.time() - t0


def run_round(jobs, repo, llm, workers):
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda j: run_job(j[1], j[2], repo, llm), jobs))
    return {j[0]: r for j, r in zip(jobs, results)}, time.time() - t0


def compare(base, other) -> dict:
    """1회차(base)와 다른 회차 비교. 반환: 칸별 다른 줄 수와 예시."""
    out = {"줄": 0, "판정 다름": 0, "설명 쪽 다름": 0, "검사 실패": 0, "사실 다름": 0, "문장 같음": 0, "설명 줄": 0,
           "예외": 0, "diffs": []}
    for job, (sig_b, _, _) in base.items():
        sig_o, err, _ = other.get(job, (None, "결과 없음", 0))
        if sig_o is None or sig_b is None:
            out["예외"] += 1
            out["diffs"].append({"job": job, "kind": "예외", "detail": err})
            continue
        for fid, b in sig_b.items():
            o = sig_o.get(fid)
            out["줄"] += 1
            if o is None:
                out["판정 다름"] += 1
                out["diffs"].append({"job": job, "id": fid, "kind": "줄 없음"})
                continue
            if o["verdict"] != b["verdict"]:
                out["판정 다름"] += 1
                out["diffs"].append({"job": job, "id": fid, "kind": "판정", "base": b["verdict"], "other": o["verdict"]})
            if b["text"] is None:
                continue
            out["설명 줄"] += 1
            out["검사 실패"] += o["checked"] is False
            if o["by"] != b["by"]:
                out["설명 쪽 다름"] += 1
                out["diffs"].append({"job": job, "id": fid, "kind": "설명 쪽", "base": b["by"], "other": o["by"]})
            if o["facts"] != b["facts"]:
                out["사실 다름"] += 1
                out["diffs"].append({"job": job, "id": fid, "kind": "사실", "base": b["facts"], "other": o["facts"],
                                     "base_text": b["text"], "other_text": o["text"]})
            out["문장 같음"] += o["text"] == b["text"]
    return out


def seconds(rnd) -> list:
    return [s["seconds"] for sig, _, _ in rnd.values() if sig for s in sig.values() if s.get("seconds")]


def pct(a, b) -> str:
    return f"{a}/{b} ({100 * a / b:.1f}%)" if b else "-"


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="추출 JSON 파일 또는 폴더")
    ap.add_argument("--db", action="store_true", help="실제 HTODB(로컬 PostgreSQL). 없으면 샘플 CSV")
    ap.add_argument("--model", help="configs/models.yaml 모델 태그. 없으면 문장틀 설명만(판정 흔들림만 본다)")
    ap.add_argument("--repeat", type=int, default=3, help="순차 회차 수(1회차가 기준). 기본 3")
    ap.add_argument("--concurrency", type=int, default=1, help="2 이상이면 동시 요청 회차를 하나 더 돈다(동시 수)")
    ap.add_argument("--out", help="보고서·달라진 줄 목록을 쓸 폴더(저장소 밖)")
    a = ap.parse_args()
    repo = None if a.db else CsvRepo()
    llm = ChatExplainer(a.model) if a.model else None
    if llm is not None:
        ok, msg = llm.ping()
        print(msg)
        if not ok:
            sys.exit(2)
    jobs = []
    for path in _files(a.paths):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("msds"):
            jobs += [(f"{path.stem}#{i}", doc, i) for i in range(len(doc["msds"]))]
    rounds = []
    for r in range(max(a.repeat, 1)):
        rnd, wall = run_round(jobs, repo, llm, 1)
        rounds.append((f"순차 {r + 1}회차", rnd, wall))
        print(f"{rounds[-1][0]}: {wall:.0f}초")
    if a.concurrency > 1:
        rnd, wall = run_round(jobs, repo, llm, a.concurrency)
        rounds.append((f"동시 {a.concurrency}개", rnd, wall))
        print(f"{rounds[-1][0]}: {wall:.0f}초")

    base = rounds[0][1]
    lines = [f"# 결과 흔들림 확인 ({time.strftime('%Y-%m-%d %H:%M')})", "",
             f"- 입력: 요청 {len(jobs)}건(MSDS 단위) · 지식: {'실제 HTODB' if a.db else '샘플 CSV'} · 설명: {a.model or '문장틀만'}",
             f"- 기준: 순차 1회차. 판정은 판정·유형·심각도·우리 값·MSDS 값·원인 코드를, 설명은 쓴 쪽·검사·글 속 숫자·코드·구분·문장을 비교",
             "", "| 회차 | 판정 다름 | 예외 | 설명 쪽 다름 | 검사 실패 | 사실(숫자·코드·구분) 다름 | 문장 완전히 같음 | 줄당 LLM 시간 중앙값·95% | 회차 시간 |",
             "|---|---|---|---|---|---|---|---|---|"]
    all_diffs = {}
    for name, rnd, wall in rounds:
        c = compare(base, rnd)
        s = sorted(seconds(rnd))
        t = f"{statistics.median(s):.2f}초 · {s[int(0.95 * (len(s) - 1))]:.2f}초" if s else "-"
        lines.append(f"| {name} | {pct(c['판정 다름'], c['줄'])} | {c['예외']} | {pct(c['설명 쪽 다름'], c['설명 줄'])} | "
                     f"{c['검사 실패']} | {pct(c['사실 다름'], c['설명 줄'])} | {pct(c['문장 같음'], c['설명 줄'])} | {t} | {wall:.0f}초 |")
        all_diffs[name] = c["diffs"]
        print(lines[-1])
    lines += ["", "- 1회차 줄은 자기 자신과 비교한 값이다(판정 다름 0, 문장 같음 100%가 정상).",
              "- 판정 다름이 하나라도 있으면 버그다. 동시 회차에서만 나오면 지식DB 접속 실패(근거부족으로 바뀜)부터 본다.",
              "- 사실 다름은 같은 줄의 설명에 들어간 숫자·코드·구분이 달라진 경우다. 문장만 다르고 사실이 같으면 표현 차이다."]
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "stability.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (out / "diffs.json").write_text(json.dumps(all_diffs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"보고서: {out / 'stability.md'}")


if __name__ == "__main__":
    main()
