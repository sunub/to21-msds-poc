"""다시 읽기 (역할 B, 개발 전용, ADR-029): 저장된 모델 응답을 서버 없이 지금 코드로 다시 읽어 펼치고 실버로 채점한다.

읽기·펼치기 고침의 효과를 RunPod 재실행 없이, 모델 흔들림 없이 잰다.
- 행 형식 항(mode rows)은 raw_text를 지금의 parse_rows로 다시 읽는다. 그 밖의 항은 ok일 때만 저장된 parsed를 쓴다.
- 원래 실행 폴더(runs/<실행>/)에는 아무것도 쓰지 않는다. --out을 주면 펼친 문서를 <DIR>/outputs/에 쓴다.
- 평가용 문서가 실행 결과에 있으면 멈춘다 (D-43).

사용법 (backend/에서)
  python scripts/replay_run.py 20261030_sections_qwen36_35b_runpod_s7_v9_cls_dev10_r1 \
      --pages-dir ../data/pages/prev/version9
  python scripts/replay_run.py <실행> --pages-dir <쪽 글자 폴더> --json      # 요약 JSON 하나만 출력
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

import _common  # noqa: F401  (src 경로 등록)
from msds.common import manifest, paths
from msds.evaluate.score import WEIGHTS, score_set
from msds.extract.expand import to_to21
from msds.extract.inputs import load_document
from msds.extract.rows import parse_rows


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _section_value(rec: dict) -> dict | None:
    """raw 기록 하나 → 펼치기에 넘길 항 응답. 행 형식 항은 raw_text를 지금 파서로 다시 읽는다."""
    if rec.get("mode") == "rows" and isinstance(rec.get("raw_text"), str):
        parsed, _ = parse_rows(rec["raw_text"], rec["section"])
        return parsed or None
    return rec.get("parsed") if rec.get("ok") else None


def replay_document(run_dir: Path, doc_id: str, pages_dir: Path, doc_meta: dict, engine: str) -> dict:
    """run_dir/raw/의 <doc_id>_m<i>_s<NN>.json을 지금 코드로 다시 읽어 TO21 문서 dict를 돌려준다.
    raw 파일이 없는 항은 넘기지 않아 펼치기가 missing_section으로 남긴다."""
    doc = load_document(doc_id, Path(pages_dir), paths.DATA / "sections", paths.DATA / "codes")
    parts: list[dict[int, dict | None]] = [{} for _ in doc.msds]
    for f in sorted((Path(run_dir) / "raw").glob(f"{doc_id}_m*_s*.json")):
        rec = _read_json(f)
        parts[rec["msds_index"]][rec["section"]] = _section_value(rec)
    out, _ = to_to21(doc_meta, parts, doc.lines, engine)
    return out


def _run_folder(run: str | Path) -> Path:
    """실행 이름이면 runs/<이름>, 경로(Path 또는 '/'가 든 글자)면 그 폴더."""
    if isinstance(run, Path) or "/" in str(run):
        return Path(run)
    return paths.run_dir(run)


def _replay(run: str | Path, pages_dir: Path | None, gold_dir: Path | None,
            out_dir: Path | None) -> tuple[str, dict]:
    """다시 읽어 채점한다. 반환: (실행 이름, score_set 결과)."""
    folder = _run_folder(run)
    info_path = folder / "run_info.yaml"
    if not info_path.exists():
        raise ValueError(f"실행 폴더나 run_info.yaml이 없습니다: {folder}")
    info = yaml.safe_load(info_path.read_text(encoding="utf-8")) or {}
    if pages_dir:
        pages = Path(pages_dir)
    elif info.get("pages_dir"):
        pages = paths.ROOT / info["pages_dir"]
    else:
        pages = None
    if pages is None or not pages.is_dir():
        raise ValueError(f"쪽 글자 폴더가 없습니다({pages}). --pages-dir로 쪽 글자 폴더를 주세요")
    gold_dir = Path(gold_dir) if gold_dir else paths.SILVER / "claude"

    outputs = sorted(p.stem for p in (folder / "outputs").glob("*.json"))
    purpose = {r["doc_id"]: r["purpose"] for r in manifest.load()}
    evals = [d for d in outputs if purpose.get(d) == "평가"]
    if evals:
        raise ValueError(f"평가용 문서는 다시 읽지 않습니다({', '.join(evals)}) (D-43)")
    docs = [d for d in outputs if (gold_dir / f"{d}.json").exists()]
    if not docs:
        raise ValueError(f"채점할 문서가 없습니다: {folder / 'outputs'}의 문서 중 {gold_dir}에 정답이 있는 것이 없음")

    engine = f"{info.get('model_tag')}:{info.get('model')} (replay)"
    pairs = []
    for d in docs:
        out = replay_document(folder, d, pages, manifest.get(d), engine)
        if out_dir:
            path = Path(out_dir) / "outputs" / f"{d}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        pairs.append((d, _read_json(gold_dir / f"{d}.json"), out))
    return folder.name, score_set(pairs)


def _summary(name: str, ss: dict) -> dict:
    return {"run": name, "docs": len(ss["docs"]), "weighted": round(ss["weighted"], 1),
            "must_pass": ss["must_passed_count"], "must_total": ss["must_total"],
            "items": {i["name"]: round(i["score"] * 100, 1) for i in ss["items"]},
            "doc_weighted": {d: round(v["weighted"], 1) for d, v in ss["docs"].items()}}


def replay_run(run: str | Path, pages_dir: Path | None = None, gold_dir: Path | None = None,
               out_dir: Path | None = None) -> dict:
    """실행 하나를 다시 읽어 채점한 요약 dict.
    키: run, docs, weighted, must_pass(필수 항목 중 평균 점수가 목표 이상인 수), must_total, items(0~100), doc_weighted."""
    return _summary(*_replay(run, pages_dir, gold_dir, out_dir))


def loss_lines(ss: dict) -> list[str]:
    """항목마다 '중요도 점수 깎은점수 항목 이름'. 깎은 점수 = 무게 × (100 − 점수) ÷ 무게 합, 큰 순서."""
    total = sum(WEIGHTS[i["level"]] for i in ss["items"])
    rows = [(WEIGHTS[i["level"]] * (100 - i["score"] * 100) / total, i) for i in ss["items"]]
    rows.sort(key=lambda r: r[0], reverse=True)
    return [f"{i['level']} {i['score'] * 100:5.1f} {loss:4.1f} {i['name']}" for loss, i in rows]


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description="저장된 모델 응답을 지금 코드로 다시 읽어 펼치고 정답과 채점한다")
    ap.add_argument("run", help="실행 이름(runs/<이름>) 또는 실행 폴더 경로")
    ap.add_argument("--pages-dir", type=Path, help="쪽 글자 폴더 (없으면 run_info.yaml의 pages_dir)")
    ap.add_argument("--gold-dir", type=Path, help="정답 폴더 (없으면 data/silver/claude)")
    ap.add_argument("--out", type=Path, help="펼친 문서를 <DIR>/outputs/에 쓴다")
    ap.add_argument("--json", action="store_true", help="요약 JSON 하나만 출력한다")
    a = ap.parse_args(argv)
    try:
        name, ss = _replay(a.run, a.pages_dir, a.gold_dir, a.out)
    except (KeyError, ValueError) as e:
        ap.error(e.args[0])
    summary = _summary(name, ss)
    if a.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"가중 종합 {summary['weighted']:.1f} · 필수 통과 {summary['must_pass']}/{summary['must_total']}")
        print("\n".join(loss_lines(ss)))
    return summary


if __name__ == "__main__":
    main()
