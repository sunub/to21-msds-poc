"""업로드한 PDF 한 건을 처음부터 끝까지 처리한다 (서비스 API).

1 전처리     preprocess_step          version17(pdf_pipeline). MSDS_PREPROCESS=legacy 면 예전 전처리 쪽 이미지·쪽 글 → data/pages/<번호>/  (쪽마다 page 이벤트)
2 항목 나누기 write_sections           16개 항 경계 → <서비스 폴더>/sections/<번호>.json
3 모델 추출   section_runner.run_document  항별 동시 호출 (plan, section_started, section_done 이벤트)
4 정리·검증   run_document 안의 펼치기·검사 (finalize 이벤트) → <서비스 폴더>/runs/<번호>/

진행은 store.apply로 바로 저장한다. 어느 단계에서 실패해도 예외를 밖으로 내지 않고 failed로 남긴다.
글꼴이 깨진 쪽은 전처리가 PaddleOCR로 읽는다. 텍스트층을 믿기 어려운 문서에는 확인 안내를 남긴다 (progress.UNTRUSTED_TEXT_LAYERS).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from msds.common import paths
from msds.extract.section_runner import raw_path, run_document, save_run_info
from msds.preprocess.section_contract import extract_sections
from msds.service.preprocess_v17 import preprocess_v17
from msds.service.store import DocumentStore

# 시험 단계에서는 RunPod vLLM으로 돌린다. 다른 모델은 configs/models.yaml 태그를 환경변수로 준다.
DEFAULT_MODEL_TAG = "qwen36_35b_runpod"
MODEL_TAG_ENV = "MSDS_SERVICE_MODEL"


PREPROCESS_ENV = "MSDS_PREPROCESS"   # legacy 이면 예전 전처리(preprocess.render.preprocess), 아니면 version17


def preprocess_step(*args, **kwargs) -> dict:
    """호출 때마다 MSDS_PREPROCESS를 읽어 version17 또는 예전 전처리로 보낸다."""
    if (os.environ.get(PREPROCESS_ENV) or "").strip().lower() == "legacy":
        from msds.preprocess.render import preprocess
        return preprocess(*args, **kwargs)
    return preprocess_v17(*args, **kwargs)


def model_tag() -> str:
    return os.environ.get(MODEL_TAG_ENV) or DEFAULT_MODEL_TAG


def service_root() -> Path:
    return paths.DATA / "service"


def write_sections(doc_id: str, pages_dir: Path, sections_dir: Path) -> dict:
    """항목 경계 파일을 쓴다. 제목을 하나도 못 찾으면 쓰지 않는다(run_document가 임시 분할·대체 경로로 간다).
    반환: 경계 통계(found, msds, complete, missing)."""
    result = extract_sections(doc_id, Path(pages_dir) / doc_id)
    stats = result["stats"]
    if result["msds"] and stats["found"]:
        Path(sections_dir).mkdir(parents=True, exist_ok=True)
        (Path(sections_dir) / f"{doc_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                                           encoding="utf-8")
    return stats


@dataclass
class Steps:
    """단계 함수. 시험에서 가짜로 바꿔 끼운다."""
    preprocess: Callable = field(default=preprocess_step)
    sections: Callable = field(default=write_sections)
    save_run_info: Callable = field(default=save_run_info)
    extract: Callable = field(default=run_document)


def process(store: DocumentStore, doc_id: str, steps: Steps | None = None, *,
            pages_dir: Path | None = None, work_dir: Path | None = None) -> None:
    """doc_id 한 건을 처리한다. pages_dir 기본은 data/pages(전처리가 쓰는 곳), work_dir 기본은 store.root."""
    steps = steps or Steps()
    pages_dir = Path(pages_dir or paths.PAGES)
    work_dir = Path(work_dir or store.root)
    sections_dir, runs_dir = work_dir / "sections", work_dir / "runs"
    tag = store.get(doc_id)["model_tag"]

    def emit(event: dict) -> None:
        store.apply(doc_id, event)

    try:
        emit({"type": "started"})
        meta = steps.preprocess(store.pdf_path(doc_id), doc_id, force=True,
                                on_page=lambda page, total: emit({"type": "page", "page": page, "total": total}))
        emit({"type": "preprocess_done", "page_count": meta["page_count"], "text_layer": meta.get("text_layer")})

        emit({"type": "stage", "stage": "sections"})
        steps.sections(doc_id, pages_dir, sections_dir)

        emit({"type": "stage", "stage": "extract"})
        steps.save_run_info(runs_dir / doc_id, tag, pages_dir)
        summary = steps.extract(doc_id, tag, doc_id, pages_dir=pages_dir, sections_dir=sections_dir,
                                runs_dir=runs_dir, on_event=emit)
        emit({"type": "done", "summary": summary})
    except Exception as e:   # 한 건의 실패가 작업자를 멈추지 않게 상태로 남긴다
        emit({"type": "failed", "error": f"{type(e).__name__}: {str(e)[:500]}"})


def result_paths(store: DocumentStore, doc_id: str) -> tuple[Path, Path]:
    """(TO21 JSON, checks JSON) 경로."""
    run = store.root / "runs" / doc_id
    return run / "outputs" / f"{doc_id}.json", run / "checks" / f"{doc_id}.json"


def section_raw_path(store: DocumentStore, doc_id: str, msds_index: int, section: int) -> Path:
    """항 하나의 모델 응답 기록. 그 항이 끝나는 즉시 생긴다."""
    return raw_path(store.root / "runs" / doc_id, doc_id, msds_index, section)
