"""추출 파인튜닝 학습 데이터 만들기 (11/03 F). 교사(GPT·Claude) 항목별 추출 결과 → train.jsonl·val.jsonl.

먼저 교사 결과를 지금 추출과 같은 항목별 방식으로 만든다(예전 run_silver.py 묶음 방식은 쓰지 않는다).
  python scripts/run_sections.py --model gpt --all-in-pages-dir --pages-dir ../data/pages/<새 문서 폴더>
  python scripts/run_sections.py --model claude --docs <문서 번호들> --pages-dir ...

그다음 (backend/에서)
  python scripts/ft_build_data.py ../runs/<교사 실행> [../runs/<교사 실행2> ...] --student qwen3_30b_a3b_rngd \\
      --out ../data/finetune/<이름>
  --student  학생 모델의 configs/models.yaml 태그. 행 형식 항(rows_sections)·JSON 방식·이미지 여부를 그 설정에서 읽는다.
             모델이 아직 안 정해졌으면 빼도 된다(지금 RNGD 설정과 같은 기본값). 정해지면 그 태그로 다시 만든다
  같은 (문서, MSDS, 항)이 여러 실행에 있으면 앞에 적은 실행의 것을 쓴다(예: Claude 실행을 먼저 적으면 Claude 우선).
  앞 실행의 것이 버려졌으면 다음 실행의 것을 쓴다
  --pages-dir 교사 실행의 run_info.yaml에 적힌 쪽 글자 폴더 대신 쓸 폴더(모든 실행에 같이 쓴다)

결과(--out): train.jsonl, val.jsonl(문서 단위로 나눔), data_info.yaml(설정·버린 수, 안내문 글은 넣지 않음), report.md
학습 파일에는 명세서로 만든 안내문과 MSDS 원문이 들어 있다. 저장소에 올리지 않는다(.gitignore data/finetune/, D-47).
manifest의 개발·평가 문서는 학습에 넣지 않는다(D-43). --allow-held-out은 코드 시험용이다.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

import _common  # noqa: F401
from msds.extract.client import load_model_config
from msds.extract.inputs import EXTRACT_SECTIONS
from msds.finetune.dataset import Student, TeacherRun, build_examples, data_info, report_md, split_by_doc


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", help="교사 실행 폴더 runs/<실행> (앞에 적은 것이 우선)")
    ap.add_argument("--student", help="학생 모델의 models.yaml 태그. 없으면 RNGD 설정과 같은 기본값")
    ap.add_argument("--out", required=True, help="결과 폴더. 예: ../data/finetune/20261104_gpt_claude80")
    ap.add_argument("--pages-dir", help="쪽 글자 폴더(교사 run_info.yaml 대신)")
    ap.add_argument("--sections", type=int, nargs="+", default=list(EXTRACT_SECTIONS), help="쓸 항. 기본은 추출 대상 항 전부")
    ap.add_argument("--val-ratio", type=float, default=0.1, help="검증용 문서 비율(문서 단위). 기본 0.1")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--allow-held-out", action="store_true", help="manifest 개발·평가 문서도 넣는다(코드 시험용. 실제 학습에 쓰지 않는다)")
    a = ap.parse_args()

    student = Student.from_config(load_model_config(a.student) if a.student else None)
    pages = Path(a.pages_dir) if a.pages_dir else None
    runs = [TeacherRun.load(Path(r), pages) for r in a.runs]
    for r in runs:
        print(f"교사 실행 {r.name}: {r.info.get('model_tag')} ({r.info.get('model')}), 안내문 {r.info.get('prompt_version')}, "
              f"쪽 글자 {r.pages_dir}")
    result = build_examples(runs, student, allow_held_out=a.allow_held_out, sections=tuple(a.sections))
    if not result.examples:
        print("만든 예시가 없습니다. report의 버린 이유를 보세요.")
    train, val, val_docs = split_by_doc(result.examples, a.val_ratio, a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "train.jsonl", train)
    write_jsonl(out / "val.jsonl", val)
    info = data_info(runs, student, result, val_docs)
    (out / "data_info.yaml").write_text(yaml.safe_dump(info, allow_unicode=True, sort_keys=False), encoding="utf-8")
    report = report_md(info, result, len(train), len(val))
    (out / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"결과: {out}")


if __name__ == "__main__":
    main()
