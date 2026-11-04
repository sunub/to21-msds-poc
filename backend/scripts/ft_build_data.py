"""추출 파인튜닝 학습 데이터 만들기 (11/03 F). 교사(GPT·Claude) 추출 결과 → train.jsonl·val.jsonl.

교사 결과는 두 가지 중 하나 또는 둘 다 넣는다.
  --silver  묶음 방식 실버 폴더(data/silver/<모델>/, 완성 TO21 문서). 11/03 팀원 p6 실버(api_opus·cli_opus·cli_codex)가 이것이다.
            근거 원문 조각으로 줄 번호를 되찾아 항별 정답으로 바꾼다(msds.finetune.from_silver). --pages-dir가 필요하다
  runs      항목별 교사 실행 폴더 runs/<실행>/ (scripts/run_sections.py --model gpt|claude). 그대로 쓴다

검증(학습 중 검증 손실)은 기본으로 개발 문서의 골드(data/gold/)를 같은 방법으로 바꿔 쓴다(--val-gold).
평가 문서는 학습에도 검증에도 넣지 않는다(D-43). --val-gold 없음이면 학습 문서의 10%를 문서 단위로 뗀다.

사용법 (backend/에서)
  python scripts/ft_build_data.py --silver ../data/silver/api_opus ../data/silver/cli_opus ../data/silver/cli_codex \\
      --pages-dir ../data/pages --student qwen3_30b_a3b_rngd --out ../data/finetune/<이름>
  --student   학생 모델의 configs/models.yaml 태그(행 형식 항·JSON 방식·이미지 여부). 없으면 지금 RNGD 설정과 같은 기본값
  --pages-dir 쪽 글자 폴더. 실버를 만들 때와 같은 전처리 판이 좋다(근거 조각을 그 글에서 찾는다)
  같은 (문서, MSDS, 항)이 여러 곳에 있으면 앞에 적은 것을 쓰고, 그것이 버려졌으면 다음 것을 쓴다

결과(--out): train.jsonl, val.jsonl, data_info.yaml(설정·살아남은 비율·버린 수, 안내문 글 없음), report.md
학습 파일에는 명세서로 만든 안내문과 MSDS 원문이 들어 있다. 저장소에 올리지 않는다(.gitignore data/finetune/, D-47).
manifest의 개발·평가 문서는 학습에 넣지 않는다(D-43). --allow-held-out은 코드 시험용이다.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

import _common  # noqa: F401
from msds.common import manifest
from msds.common.paths import DATA
from msds.extract.client import load_model_config
from msds.extract.inputs import EXTRACT_SECTIONS
from msds.finetune.dataset import (SilverSet, Student, TeacherRun, build_examples, data_info, report_md,
                                   split_by_doc)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def dev_docs() -> set[str]:
    return {r["doc_id"] for r in manifest.load() if r.get("purpose") == "개발"}


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", help="항목별 교사 실행 폴더 runs/<실행>")
    ap.add_argument("--silver", nargs="*", default=[], help="묶음 방식 실버 폴더 data/silver/<모델>")
    ap.add_argument("--student", help="학생 모델의 models.yaml 태그. 없으면 RNGD 설정과 같은 기본값")
    ap.add_argument("--out", required=True, help="결과 폴더. 예: ../data/finetune/20261104_silver59")
    ap.add_argument("--pages-dir", help="쪽 글자 폴더(실버에 필요. 교사 실행에는 run_info.yaml 대신 쓴다)")
    ap.add_argument("--val-gold", default=str(DATA / "gold"), help="검증용 골드 폴더(개발 문서만 쓴다). 'none'이면 학습 문서에서 뗀다")
    ap.add_argument("--val-pages-dir", help="검증 골드의 쪽 글자 폴더(기본 --pages-dir, 없으면 data/pages)")
    ap.add_argument("--sections", type=int, nargs="+", default=list(EXTRACT_SECTIONS), help="쓸 항. 기본은 추출 대상 항 전부")
    ap.add_argument("--val-ratio", type=float, default=0.1, help="--val-gold none일 때 학습 문서에서 뗄 비율(문서 단위)")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--allow-held-out", action="store_true", help="manifest 개발·평가 문서도 학습에 넣는다(코드 시험용)")
    a = ap.parse_args()
    if not a.runs and not a.silver:
        ap.error("교사 실행(runs) 또는 --silver 중 하나는 있어야 합니다")
    if a.silver and not a.pages_dir:
        ap.error("--silver에는 --pages-dir가 필요합니다(근거 조각을 쪽 글자에서 찾는다)")

    student = Student.from_config(load_model_config(a.student) if a.student else None)
    pages = Path(a.pages_dir) if a.pages_dir else None
    sources = [SilverSet(Path(s), pages) for s in a.silver] + [TeacherRun.load(Path(r), pages) for r in a.runs]
    for s in sources:
        d = s.describe()
        print(f"교사 {d['run']} ({d['kind']}): {d['model'] or d['model_tag']}, 쪽 글자 {s.pages_dir}")
    sections = tuple(a.sections)
    result = build_examples(sources, student, allow_held_out=a.allow_held_out, sections=sections)
    if not result.examples:
        print("만든 예시가 없습니다. report의 버린 이유를 보세요.")

    val_result = None
    if a.val_gold and a.val_gold.lower() != "none":
        dev = dev_docs()
        val_pages = Path(a.val_pages_dir or a.pages_dir or DATA / "pages")
        val_result = build_examples([SilverSet(Path(a.val_gold), val_pages, "gold")], student, allow_held_out=True,
                                    sections=sections, only_docs=dev)     # 개발 문서만. 평가 문서는 넣지 않는다 (D-43)
        overlap = {e["doc_id"] for e in result.examples} & {e["doc_id"] for e in val_result.examples}
        if overlap:
            sys.exit(f"학습과 검증에 같은 문서가 있습니다: {sorted(overlap)}")
        train, val = result.examples, val_result.examples
        val_docs = sorted({e["doc_id"] for e in val})
    else:
        train, val, val_docs = split_by_doc(result.examples, a.val_ratio, a.seed)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "train.jsonl", train)
    write_jsonl(out / "val.jsonl", val)
    info = data_info(sources, student, result, val_docs, val_result)
    (out / "data_info.yaml").write_text(yaml.safe_dump(info, allow_unicode=True, sort_keys=False), encoding="utf-8")
    report = report_md(info, result, len(train), len(val))
    (out / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"결과: {out}")


if __name__ == "__main__":
    main()
