"""Real PostgreSQL integration, opt in with a disposable MSDS_TEST_DATABASE_URL."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import threading
import uuid

import pymupdf
import psycopg
from psycopg import sql
import pytest

from msds.preprocess.jobs import JobStore, run_one
from msds.preprocess.pdf_pipeline import extract_pdf


@pytest.fixture
def pg_store():
    dsn = os.environ.get('MSDS_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set MSDS_TEST_DATABASE_URL to a disposable PostgreSQL database')
    # Quote in the name checks that every schema reference uses SQL identifiers,
    # rather than unsafe string interpolation.
    schema = 'test_extraction_"' + uuid.uuid4().hex
    # A unique schema makes cleanup scoped even if other tests use the database.
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        yield JobStore(dsn, schema=schema), dsn, schema
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def create_pdf(path: Path):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((32, 60), 'Fresh product CAS 71-43-2')
        doc.save(path)


def test_postgres_claims_once_persists_and_publishes(pg_store, tmp_path):
    store, dsn, schema = pg_store
    pdf, output = tmp_path / 'input.pdf', tmp_path / 'pages' / 'doc_one'
    create_pdf(pdf)
    store.create_job('job_one', 'doc_one', pdf, output, 'input.pdf')
    first_started, release = threading.Event(), threading.Event()
    calls = []

    def delayed_extractor(source, out, **kwargs):
        calls.append(1)
        first_started.set()
        assert release.wait(10)
        return extract_pdf(source, out, **kwargs)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run_one, store, delayed_extractor, ocr_device='cpu', use_docling=False)
        assert first_started.wait(10)
        assert JobStore(dsn, schema=schema).get_job('job_one')['status'] == 'running'
        second = executor.submit(run_one, JobStore(dsn, schema=schema), delayed_extractor, ocr_device='cpu', use_docling=False)
        assert second.result(timeout=10) is False
        release.set()
        assert first.result(timeout=20) is True
    assert calls == [1]
    job = JobStore(dsn, schema=schema).get_job('job_one')
    assert job['status'] == 'succeeded'
    assert job['completed_pages'] == job['total_pages'] == 1
    assert '71-43-2' in (output / 'p001.txt').read_text(encoding='utf-8')
    assert (output / 'p001.png').is_file()


def test_postgres_reports_worker_failure(pg_store, tmp_path):
    store, dsn, schema = pg_store
    source, output = tmp_path / 'input.pdf', tmp_path / 'pages' / 'doc_two'
    create_pdf(source)
    store.create_job('job_two', 'doc_two', source, output, 'input.pdf')
    def fail(*args, **kwargs):
        raise RuntimeError('extraction failed')
    assert run_one(store, extractor=fail)
    job = JobStore(dsn, schema=schema).get_job('job_two')
    assert job['status'] == 'failed' and job['error']
    assert job['result_dir'] is None and not output.exists()


def test_schema_and_job_ids_are_safely_composed(monkeypatch):
    """Render every statement without a server to catch SQL identifier injection."""
    statements = []
    attack_job = "job'; DROP SCHEMA public;--"
    schema = 'quoted"; DROP SCHEMA public;--'

    class FakeResult:
        rowcount = 1
        def fetchone(self):
            return {'job_id': attack_job}

    class FakeConnection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, statement, params=None):
            rendered = statement if isinstance(statement, str) else statement.as_string()
            statements.append((rendered, params))
            return FakeResult()

    monkeypatch.setattr(psycopg, 'connect', lambda *a, **k: FakeConnection())
    store = JobStore('postgresql://unused', schema=schema)
    store.create_job(attack_job, 'doc_test', '/tmp/in.pdf', '/tmp/out', 'in.pdf')
    store.get_job(attack_job)
    store.recover_expired()
    store.claim('worker', 5)
    store.heartbeat(attack_job, 'worker', 5)
    store.progress(attack_job, 'worker', {'stage': 'page', 'completed_pages': 1, 'total_pages': 2})
    store.finish(attack_job, 'worker', result_dir='/tmp/out')
    table = '"quoted""; DROP SCHEMA public;--"."extraction_jobs"'
    job_queries = [query for query, _ in statements if 'extraction_jobs' in query]
    assert len(job_queries) >= 8
    assert all(table in query for query in job_queries)
    assert all(attack_job not in query for query, _ in statements)
    assert any(attack_job in params for _, params in statements if params)
