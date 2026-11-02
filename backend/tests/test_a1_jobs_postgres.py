"""Real PostgreSQL tests; set MSDS_TEST_DATABASE_URL to a disposable database."""
from __future__ import annotations

import os
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from msds.service.jobs import LeaseLost, PostgresJobStore, ReviewNotReady
from msds.service.store import DocumentStore
from msds.service.worker import PostgresWorker


@pytest.fixture
def store(tmp_path):
    dsn = os.environ.get('MSDS_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set MSDS_TEST_DATABASE_URL to a disposable PostgreSQL database')
    schema = 'test_a1_' + uuid.uuid4().hex
    migration = Path(__file__).resolve().parents[1] / 'migrations/a1_0001_extract_jobs.sql'
    ddl = migration.read_text(encoding='utf-8').replace('extract.jobs', f'"{schema}".jobs')
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        db.execute(ddl)
    try:
        yield PostgresJobStore(dsn, tmp_path / 'uploads', schema=schema)
    finally:
        with psycopg.connect(dsn, autocommit=True) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def new_job(store, filename='a.pdf'):
    return store.create(b'%PDF-1.7\ntest', filename, None, 'model', today='20261103')


def test_db_create_leaves_no_file_mode_state_and_preserves_orphan_on_failure(store):
    with pytest.raises(psycopg.Error):
        store.create(b'%PDF-1.7\ntest', 'bad.pdf', '2026-99-99', 'model', today='20261103')
    orphan = store.root / 'U-20261103-001'
    assert (orphan / 'source.pdf').exists()
    assert not (orphan / 'state.json').exists()
    created = new_job(store)
    assert created['id'] == 'U-20261103-002'
    assert created['duplicate_of'] == []
    assert not (store.root / created['id'] / 'state.json').exists()
    assert DocumentStore(store.root).recover() == []


def test_concurrent_creates_allocate_unique_ids_and_db_duplicates(store):
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(lambda n: new_job(store, f'{n}.pdf'), range(2)))
    jobs.sort(key=lambda job: job['id'])
    assert [job['id'] for job in jobs] == ['U-20261103-001', 'U-20261103-002']
    assert jobs[0]['duplicate_of'] == [] and jobs[1]['duplicate_of'] == [jobs[0]['id']]


def test_competing_workers_claim_only_once_and_keep_pdf(store):
    created = new_job(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(2)))
    claims = [claim for claim in claims if claim is not None]
    assert len(claims) == 1
    assert claims[0]['id'] == created['id']
    assert store.pdf_path(created['id']).read_bytes().startswith(b'%PDF-')
    assert store.get(created['id'])['status'] == 'running'


def test_separate_stages_fence_stale_worker_and_finish(store):
    job = new_job(store)
    first = store.claim()
    first_token = first['lease_token']
    worker = store.bind(job['id'], first_token)
    worker.apply(job['id'], {'type': 'page', 'page': 1, 'total': 1})
    store.queue_next(job['id'], first_token)
    assert store.claim(stage='preprocess') is None
    second = store.claim(stage='extract')
    assert second['id'] == job['id']
    with pytest.raises(LeaseLost):
        worker.apply(job['id'], {'type': 'stage', 'stage': 'extract'})
    assert not store.heartbeat(job['id'], first_token)
    store.bind(job['id'], second['lease_token']).apply(job['id'], {'type': 'done', 'summary': {}})
    assert store.get(job['id'])['status'] == 'running'
    assert store.finish(job['id'], second['lease_token'])['status'] == 'done'
    assert store.get(job['id'])['status'] == 'done'


def test_expired_lease_cannot_write_and_recovers_without_touching_live_jobs(store):
    old, live = new_job(store, 'old.pdf'), new_job(store, 'live.pdf')
    stale, active = store.claim(), store.claim()
    with store._connect() as db:
        db.execute(sql.SQL("UPDATE {} SET lease_expires_at=now()-interval '1 second' WHERE job_id=%s")
                   .format(store.table), (old['id'],))
    assert not store.heartbeat(old['id'], stale['lease_token'])
    with pytest.raises(LeaseLost):
        store.apply(old['id'], {'type': 'failed', 'error': 'late'}, lease_token=stale['lease_token'])
    assert store.recover_expired() == 1
    assert store.get(old['id'])['status'] == 'queued'
    restarted = store.claim()
    assert restarted['id'] == old['id']
    assert store.attempt_paths(old['id'], stale['lease_token']) != store.attempt_paths(old['id'], restarted['lease_token'])
    with pytest.raises(LeaseLost):
        store.queue_next(old['id'], stale['lease_token'])
    assert store.get(live['id'])['status'] == 'running'
    assert store.heartbeat(live['id'], active['lease_token'])


def test_stale_attempt_files_cannot_replace_current_publication(store):
    job = new_job(store)
    old = store.claim()
    old_paths = store.attempt_paths(job['id'], old['lease_token'])
    (old_paths['pages_dir'] / job['id']).mkdir(parents=True)
    (old_paths['pages_dir'] / job['id'] / 'p001.txt').write_text('stale')
    with store._connect() as db:
        db.execute(sql.SQL("UPDATE {} SET lease_expires_at=now()-interval '1 second' WHERE job_id=%s")
                   .format(store.table), (job['id'],))
    assert store.recover_expired() == 1
    fresh = store.claim()
    fresh_paths = store.attempt_paths(job['id'], fresh['lease_token'])
    (fresh_paths['pages_dir'] / job['id']).mkdir(parents=True)
    (fresh_paths['pages_dir'] / job['id'] / 'p001.txt').write_text('current')
    store.queue_next(job['id'], fresh['lease_token'])
    # The old process continues writing, but its directory is no longer published.
    (old_paths['pages_dir'] / job['id'] / 'p001.txt').write_text('late stale write')
    with pytest.raises(LeaseLost):
        store.queue_next(job['id'], old['lease_token'])
    published = store.artifact_paths(job['id'])
    assert (published['pages_dir'] / job['id'] / 'p001.txt').read_text() == 'current'


def test_one_automatic_retry_then_manual_retry(store):
    job = new_job(store)
    first = store.claim()
    assert store.finish(job['id'], first['lease_token'], error='first failure')['status'] == 'queued'
    second = store.claim()
    assert store.finish(job['id'], second['lease_token'], error='second failure')['status'] == 'failed'
    assert store.claim() is None
    assert store.requeue(job['id'])['status'] == 'queued'
    assert store.requeue(job['id']) is None
    assert store.claim()['id'] == job['id']


def test_queue_positions_and_unknown_estimate(store):
    a, b = new_job(store, 'a.pdf'), new_job(store, 'b.pdf')
    assert store.queue_info(a['id']) == {'queue_position': 1, 'estimated_wait_seconds': None, 'estimated_completion_seconds': None}
    assert store.queue_info(b['id']) == {'queue_position': 2, 'estimated_wait_seconds': None, 'estimated_completion_seconds': None}
    store.claim()
    assert store.queue_info(b['id'])['queue_position'] == 1
    assert store.queue_info(b['id'])['estimated_completion_seconds'] is None


def test_estimate_uses_measured_completions_and_running_workers(store):
    completed = [new_job(store, f'done-{n}.pdf') for n in range(3)]
    running = new_job(store, 'running.pdf')
    waiting = new_job(store, 'waiting.pdf')
    start = datetime(2026, 11, 3, tzinfo=timezone.utc)
    with store._connect() as db:
        for job, seconds in zip(completed, (10, 20, 30)):
            history = [{'attempt': 1, 'status': 'done', 'started_at': start.isoformat(),
                        'finished_at': (start + timedelta(seconds=seconds)).isoformat()}]
            db.execute(sql.SQL("UPDATE {} SET status='done', attempts_json=%s WHERE job_id=%s").format(store.table),
                       (Jsonb(history), job['id']))
        db.execute(sql.SQL("UPDATE {} SET status='running' WHERE job_id=%s").format(store.table), (running['id'],))
    assert store.queue_info(waiting['id'], workers=1) == {
        'queue_position': 1, 'estimated_wait_seconds': 30, 'estimated_completion_seconds': 60}
    assert store.queue_info(waiting['id'], workers=2) == {
        'queue_position': 1, 'estimated_wait_seconds': 0, 'estimated_completion_seconds': 30}


def test_worker_end_to_end_with_real_postgres_and_isolated_artifacts(store):
    job = new_job(store)
    attempts = []

    def preprocess(path, doc_id, *, force, on_page, pages_root):
        attempts.append(pages_root)
        page_dir = pages_root / doc_id
        page_dir.mkdir(parents=True)
        (page_dir / 'p001.txt').write_text('verified content')
        on_page(1, 1)
        if len(attempts) == 1:
            raise RuntimeError('retry this transient failure')
        return {'page_count': 1, 'text_layer': '정상'}

    def save_run_info(run, model_tag, pages_dir):
        run.mkdir(parents=True)

    def extract(doc_id, model_tag, run_name, *, pages_dir, sections_dir, runs_dir, on_event):
        assert (pages_dir / doc_id / 'p001.txt').read_text() == 'verified content'
        out = runs_dir / doc_id / 'outputs'
        out.mkdir()
        (out / f'{doc_id}.json').write_text('{"ok": true}')
        return {'sections_ok': 1}

    steps = SimpleNamespace(preprocess=preprocess, sections=lambda *args: None,
                            save_run_info=save_run_info, extract=extract)
    worker = PostgresWorker(store, steps=steps, poll_seconds=.01, lease_seconds=5)
    deadline = time.monotonic() + 15
    try:
        worker.start()
        while time.monotonic() < deadline and store.get(job['id'])['status'] != 'done':
            time.sleep(.02)
        assert store.get(job['id'])['status'] == 'done'
    finally:
        worker.stop(timeout=5)
    assert len(attempts) == 2 and attempts[0] != attempts[1]
    published = store.artifact_paths(job['id'])
    assert (published['pages_dir'] / job['id'] / 'p001.txt').read_text() == 'verified content'
    assert (published['runs_dir'] / job['id'] / 'outputs' / f"{job['id']}.json").exists()


def test_retry_waits_for_review_update_and_preserves_review_of_previous_version(store):
    job = new_job(store)
    prep = store.claim()
    store.queue_next(job['id'], prep['lease_token'])
    extraction = store.claim(stage='extract')
    bound = store.bind(job['id'], extraction['lease_token'])
    bound.apply(job['id'], {'type': 'plan', 'msds_count': 1,
                            'sections': [{'msds_index': 0, 'section': 1, 'pages': [1]}]})
    bound.apply(job['id'], {'type': 'section_done', 'msds_index': 0, 'section': 1, 'ok': False,
                            'needs_review': True, 'reextracted': True, 'errors': ['failure']})
    bound.apply(job['id'], {'type': 'done', 'summary': {}})
    store.finish(job['id'], extraction['lease_token'])
    old_token = extraction['lease_token']
    old_review = store.attempt_paths(job['id'], old_token)['runs_dir'].parent / 'review.json'
    entered, release = threading.Event(), threading.Event()

    def change(record):
        entered.set()
        assert release.wait(5)
        record['fields']['example'] = 'reviewed'

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            write = pool.submit(store.update_review, job['id'], change)
            assert entered.wait(5)
            retry = pool.submit(store.requeue, job['id'])
            with pytest.raises(TimeoutError):
                retry.result(timeout=.1)
            release.set()
            assert write.result(timeout=5)['fields']['example'] == 'reviewed'
            assert retry.result(timeout=5)['status'] == 'queued'
    finally:
        release.set()
    state = store.get(job['id'])
    assert '_active_token' not in state
    assert old_token in state['_previous_artifacts']
    assert store.artifact_paths(job['id']) is None
    assert old_review.is_file() and 'reviewed' in old_review.read_text()
    with pytest.raises(ReviewNotReady):
        store.update_review(job['id'], lambda record: None)

