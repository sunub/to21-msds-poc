"""PDF text-extraction API. Run the extraction worker separately.

The API and worker must have access to the same job database and filesystem.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pymupdf
from fastapi import FastAPI, File, HTTPException, UploadFile, status

from msds.preprocess.jobs import JobStore
from msds.preprocess.job_config import jobs_database_url

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_ROOT = ROOT / "data" / "extraction_api"
DEFAULT_PAGES_ROOT = ROOT / "data" / "pages" / "api"
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _validate_pdf(path: Path) -> None:
    try:
        document = pymupdf.open(path)
        try:
            if not document.is_pdf or document.needs_pass or not len(document):
                raise ValueError("PDF must have at least one page and must not be encrypted")
        finally:
            document.close()
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid, empty, or encrypted PDF") from exc


def _public_job(job: dict) -> dict:
    ready = job["status"] == "succeeded" and job["result_dir"] is not None
    return {
        "job_id": job["job_id"],
        "doc_id": job["doc_id"],
        "original_filename": job["original_filename"],
        "status": job["status"],
        "stage": job["stage"],
        "completed_pages": job["completed_pages"],
        "total_pages": job["total_pages"],
        "result_ready": ready,
        # The path is meaningful only on a host that shares this filesystem.
        "result_dir": job["result_dir"] if ready else None,
        "error": job["error"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "updated_at": job["updated_at"],
        "finished_at": job["finished_at"],
    }


def create_app(data_root: str | Path | None = None, *, database_url: str | None = None,
               store_factory=JobStore, max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES) -> FastAPI:
    if max_upload_bytes <= 0:
        raise ValueError("max_upload_bytes must be positive")
    # Explicit data_root keeps isolated test/deployment instances self-contained.
    if data_root is None:
        root = Path(os.environ.get("MSDS_EXTRACTION_ROOT", DEFAULT_DATA_ROOT)).expanduser().resolve()
        pages_root = Path(os.environ.get("MSDS_PAGES_ROOT", DEFAULT_PAGES_ROOT)).expanduser().resolve()
    else:
        root = Path(data_root).expanduser().resolve()
        pages_root = root / "pages"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        dsn = jobs_database_url(database_url)
        root.mkdir(parents=True, exist_ok=True)
        (root / "uploads").mkdir(parents=True, exist_ok=True)
        pages_root.mkdir(parents=True, exist_ok=True)
        app.state.store = store_factory(dsn)
        yield

    app = FastAPI(title="MSDS PDF Text Extraction", version="1.0", lifespan=lifespan)
    app.state.data_root = root
    app.state.pages_root = pages_root

    @app.post("/api/v1/documents", status_code=status.HTTP_202_ACCEPTED)
    async def create_document(file: UploadFile = File(...)):
        doc_id, job_id = f"doc_{uuid.uuid4().hex}", f"job_{uuid.uuid4().hex}"
        source_path = root / "uploads" / f"{doc_id}.pdf"
        original_filename = (file.filename or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1]
        submitted = False
        try:
            size = 0
            with source_path.open("xb") as target:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_upload_bytes:
                        raise HTTPException(status_code=413, detail="PDF exceeds the upload size limit")
                    target.write(chunk)
            if size == 0:
                raise HTTPException(status_code=422, detail="Empty PDF")
            _validate_pdf(source_path)
            # A database connection can fail while COMMIT has an unknown outcome.
            # Keep the uploaded file once submission starts so a committed job
            # can never point to an input deleted by this request.
            submitted = True
            app.state.store.create_job(job_id, doc_id, source_path, pages_root / doc_id, original_filename)
            return {"job_id": job_id, "doc_id": doc_id, "status": "queued"}
        finally:
            await file.close()
            if not submitted:
                source_path.unlink(missing_ok=True)

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str):
        job = app.state.store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return _public_job(job)

    return app


app = create_app()
