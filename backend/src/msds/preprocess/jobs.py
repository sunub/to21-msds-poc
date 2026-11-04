"""Persistent extraction jobs and a separate, single-host worker.

The API only enqueues jobs. Run this module as a separate process to execute
PDF extraction; both processes must use the same PostgreSQL database and storage.
"""
from __future__ import annotations

import argparse
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .job_config import jobs_database_url

LOG = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """PostgreSQL-backed state; one short-lived connection per operation."""

    def __init__(self, database_url: str | None = None, *, schema: str = 'msds_extraction'):
        self.database_url = jobs_database_url(database_url)
        if not isinstance(schema, str) or not schema or '\x00' in schema or len(schema.encode('utf-8')) > 63:
            raise ValueError('schema must be a nonempty PostgreSQL identifier of at most 63 bytes')
        self.schema = schema
        self.table = sql.Identifier(schema, 'extraction_jobs')
        with self._connect() as db:
            # API and worker may start together against a fresh database.
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ('msds_extraction_jobs_schema_v1:' + schema,))
            db.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            db.execute(sql.SQL("""CREATE TABLE IF NOT EXISTS {table} (
                job_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                output_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                completed_pages INTEGER NOT NULL DEFAULT 0,
                total_pages INTEGER,
                error TEXT,
                result_dir TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                updated_at TEXT NOT NULL,
                finished_at TEXT,
                worker_id TEXT,
                lease_until DOUBLE PRECISION
            )""").format(table=self.table))
            db.execute(sql.SQL("CREATE INDEX IF NOT EXISTS idx_extraction_jobs_status ON {table}(status, created_at)")
                       .format(table=self.table))

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=5) as db:
            yield db

    def create_job(self, job_id: str, doc_id: str, source_path: str | Path,
                   output_path: str | Path, original_filename: str) -> dict:
        now = _now()
        with self._connect() as db:
            row = db.execute(sql.SQL("""INSERT INTO {table}
                (job_id, doc_id, source_path, output_path, original_filename,
                 status, stage, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, 'queued', 'queued', %s, %s) RETURNING *""").format(table=self.table),
                (job_id, doc_id, str(source_path), str(output_path), original_filename, now, now)).fetchone()
        return dict(row)

    def get_job(self, job_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(sql.SQL("SELECT * FROM {table} WHERE job_id = %s").format(table=self.table), (job_id,)).fetchone()
        return dict(row) if row is not None else None

    def recover_expired(self) -> int:
        """Mark abandoned leases for investigation; never run them twice automatically."""
        now = _now()
        with self._connect() as db:
            cur = db.execute(sql.SQL("""UPDATE {table} SET status='recovery_required',
                stage='recovery_required', error=%s, updated_at=%s, finished_at=%s, worker_id=NULL,
                lease_until=NULL WHERE status='running' AND lease_until < EXTRACT(EPOCH FROM clock_timestamp())""").format(table=self.table),
                ('Worker heartbeat expired; inspect the existing output before retrying.', now, now))
            return cur.rowcount

    def claim(self, worker_id: str, lease_seconds: float) -> dict | None:
        now = _now()
        with self._connect() as db:
            row = db.execute(sql.SQL("SELECT job_id FROM {table} WHERE status='queued' ORDER BY created_at, job_id LIMIT 1 FOR UPDATE SKIP LOCKED").format(table=self.table)).fetchone()
            if row is None:
                return None
            job_id = row['job_id']
            db.execute(sql.SQL("""UPDATE {table} SET status='running', stage='preparing',
                started_at=%s, updated_at=%s, worker_id=%s,
                lease_until=EXTRACT(EPOCH FROM clock_timestamp()) + %s
                WHERE job_id=%s AND status='queued'""").format(table=self.table),
                (now, now, worker_id, lease_seconds, job_id))
            return dict(db.execute(sql.SQL("SELECT * FROM {table} WHERE job_id=%s").format(table=self.table), (job_id,)).fetchone())

    def heartbeat(self, job_id: str, worker_id: str, lease_seconds: float) -> bool:
        with self._connect() as db:
            cur = db.execute(sql.SQL("""UPDATE {table} SET lease_until=EXTRACT(EPOCH FROM clock_timestamp()) + %s
                WHERE job_id=%s AND status='running' AND worker_id=%s""").format(table=self.table),
                (lease_seconds, job_id, worker_id))
            return cur.rowcount == 1

    def progress(self, job_id: str, worker_id: str, event: dict) -> bool:
        event_stage = event.get('stage')
        stages = {'start': 'preparing', 'tables': 'tables', 'page': 'extracting', 'complete': 'publishing'}
        stage = stages.get(event_stage)
        if stage is None:
            return True
        completed = event.get('completed_pages')
        total = event.get('total_pages', event.get('page_count'))
        # A final callback can occur before this worker has recorded success.
        with self._connect() as db:
            cur = db.execute(sql.SQL("""UPDATE {table} SET stage=%s,
                completed_pages=COALESCE(%s, completed_pages), total_pages=COALESCE(%s, total_pages), updated_at=%s
                WHERE job_id=%s AND status='running' AND worker_id=%s""").format(table=self.table),
                (stage, completed, total, _now(), job_id, worker_id))
            return cur.rowcount == 1

    def finish(self, job_id: str, worker_id: str, *, error: str | None = None,
               result_dir: str | None = None) -> bool:
        now = _now()
        status = 'failed' if error is not None else 'succeeded'
        with self._connect() as db:
            cur = db.execute(sql.SQL("""UPDATE {table} SET status=%s, stage=%s, error=%s, result_dir=%s,
                updated_at=%s, finished_at=%s, lease_until=NULL, worker_id=NULL
                WHERE job_id=%s AND status='running' AND worker_id=%s""").format(table=self.table),
                (status, status, error, result_dir, now, now, job_id, worker_id))
            return cur.rowcount == 1


def run_one(store: JobStore, extractor: Callable | None = None, *, ocr_device: str = 'gpu:0',
            use_docling: bool = True, lease_seconds: float = 120) -> bool:
    """Claim and process one queued job. Return False if no job was waiting."""
    if lease_seconds <= 0:
        raise ValueError('lease_seconds must be positive')
    store.recover_expired()
    worker_id = uuid.uuid4().hex
    job = store.claim(worker_id, lease_seconds)
    if job is None:
        return False
    stop_heartbeat = threading.Event()

    def heartbeat_loop() -> None:
        while not stop_heartbeat.wait(max(0.1, lease_seconds / 3)):
            try:
                if not store.heartbeat(job['job_id'], worker_id, lease_seconds):
                    return
            except Exception:
                LOG.exception('Could not renew extraction job heartbeat')

    heartbeat = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat.start()
    try:
        if extractor is None:
            from .pdf_pipeline import extract_pdf
            extractor = extract_pdf

        def on_progress(event: dict) -> None:
            if not store.progress(job['job_id'], worker_id, event):
                raise RuntimeError('Job lease lost while extracting')

        output = Path(job['output_path'])
        extractor(Path(job['source_path']), output, doc_id=job['doc_id'], ocr_device=ocr_device,
                  use_docling=use_docling, on_progress=on_progress)
        if not output.is_dir():
            raise RuntimeError('Extraction returned without publishing the output directory')
        if not store.finish(job['job_id'], worker_id, result_dir=str(output)):
            LOG.error('Extraction finished after its job lease was lost: %s', job['job_id'])
    except Exception as exc:
        LOG.exception('Extraction job failed: %s', job['job_id'])
        store.finish(job['job_id'], worker_id, error=f'{type(exc).__name__}: {exc}'[:1000])
    finally:
        stop_heartbeat.set()
        heartbeat.join()
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Run the PDF extraction job worker')
    parser.add_argument('--database-url', help='PostgreSQL DSN (or configure the MSDS_JOBS_PG_* variables)')
    parser.add_argument('--schema', default='msds_extraction', help='PostgreSQL jobs schema')
    parser.add_argument('--ocr-device', default='gpu:0', help='OCR device (default gpu:0; use cpu when needed)')
    parser.add_argument('--no-docling', action='store_true', help='Disable auxiliary Docling table analysis')
    parser.add_argument('--poll-seconds', type=float, default=1.0)
    parser.add_argument('--lease-seconds', type=float, default=120.0)
    args = parser.parse_args(argv)
    if args.poll_seconds <= 0 or args.lease_seconds <= 0:
        parser.error('poll and lease intervals must be positive')
    logging.basicConfig(level=logging.INFO)
    try:
        store = JobStore(args.database_url, schema=args.schema)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        while True:
            if not run_one(store, ocr_device=args.ocr_device, use_docling=not args.no_docling,
                           lease_seconds=args.lease_seconds):
                time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        LOG.info('Worker stopped')


if __name__ == '__main__':
    main()
