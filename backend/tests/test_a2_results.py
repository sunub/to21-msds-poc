"""A2 불변 결과 저장. 실제 PostgreSQL 시험은 전용 테스트 DB에서만 실행한다."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
import uuid

import psycopg
from psycopg import sql
import pytest
from fastapi.testclient import TestClient

from msds.service.jobs import LeaseLost, PostgresJobStore, ReviewNotReady
from msds.service.results import ResultConflict, ResultNotReady, ResultStore, canonical_sha256
from msds.service import review
from msds.service.worker import PostgresWorker


def test_json_hash_is_canonical_and_rejects_nonfinite_values():
    assert canonical_sha256({'나': [3, 2], '가': '한글'}) == canonical_sha256({'가': '한글', '나': [3, 2]})
    with pytest.raises(ValueError):
        canonical_sha256({'bad': float('nan')})
    with pytest.raises(ValueError):
        canonical_sha256([])


@pytest.fixture
def stores(tmp_path):
    dsn = os.environ.get('MSDS_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('MSDS_TEST_DATABASE_URL에 별도 시험 DB가 필요합니다')
    schema = 'test_a2_' + uuid.uuid4().hex
    migrations = Path(__file__).resolve().parents[1] / 'migrations'
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        for name in ('a1_0001_extract_jobs.sql', 'a2_0002_extract_results_reviews_artifacts.sql'):
            ddl = (migrations / name).read_text(encoding='utf-8')
            for table in ('jobs', 'results', 'reviews', 'artifacts'):
                ddl = ddl.replace(f'extract.{table}', f'"{schema}".{table}')
            db.execute(ddl)
    try:
        yield PostgresJobStore(dsn, tmp_path / 'files', schema=schema), ResultStore(dsn, schema=schema), schema
    finally:
        with psycopg.connect(dsn, autocommit=True) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def start_extraction(store):
    job = store.create(b'%PDF-1.7\nfake', 'one.pdf', None, 'model', today='20261103')
    pre = store.claim(stage='preprocess')
    store.queue_next(job['id'], pre['lease_token'])
    return job, store.claim(stage='extract')


def test_validate_schema_checks_required_result_table(stores):
    jobs, results, _ = stores
    results.validate_schema()
    missing = ResultStore(jobs.dsn, schema='missing_a2_schema')
    with pytest.raises(RuntimeError, match='A2'):
        missing.validate_schema()


def finish(store, job, claimed):
    store.bind(job['id'], claimed['lease_token']).apply(job['id'], {'type': 'done', 'summary': {}})
    return store.complete(job['id'], claimed['lease_token'])


def test_review_events_survive_restart_and_retry_without_changing_extraction(stores):
    jobs, results, schema = stores
    job, claim = start_extraction(jobs)
    doc = {'msds': [{'product': {'name': '원본'}}]}
    jobs.bind(job['id'], claim['lease_token']).apply(job['id'], {
        'type': 'plan', 'msds_count': 1,
        'sections': [{'msds_index': 0, 'section': 1, 'pages': [1]}],
    })
    jobs.bind(job['id'], claim['lease_token']).apply(job['id'], {
        'type': 'section_done', 'msds_index': 0, 'section': 1, 'ok': False,
        'needs_review': True, 'reextracted': True, 'errors': ['확인 필요'],
    })
    results.save_for_lease(job['id'], claim['lease_token'], doc, {})
    finish(jobs, job, claim)
    jobs.update_review(job['id'], lambda record: review.set_field(
        record, doc, 0, 'product.name', 'edit', '수정', '검토자', '2026-11-03T12:00:00+09:00'))
    restarted = PostgresJobStore(jobs.dsn, jobs.root, schema=schema)
    current = restarted.load_review(job['id'])
    assert review.apply_edits(doc, current)['msds'][0]['product']['name'] == '수정'
    assert results.get_active(job['id'])['extraction'] == doc
    with psycopg.connect(jobs.dsn) as db:
        rows = db.execute(sql.SQL('SELECT result_id, action, field_path, reviewer FROM {} WHERE job_id=%s')
                          .format(sql.Identifier(schema, 'reviews')), (job['id'],)).fetchall()
    assert rows == [(f"a2-{job['id']}-{claim['lease_token']}-extraction", 'edit', 'product.name', '검토자')]
    restarted.requeue(job['id'])
    with pytest.raises(ReviewNotReady):
        restarted.load_review(job['id'])
    with psycopg.connect(jobs.dsn) as db:
        count = db.execute(sql.SQL('SELECT count(*) FROM {} WHERE job_id=%s')
                           .format(sql.Identifier(schema, 'reviews')), (job['id'],)).fetchone()[0]
    assert count == 1


def test_identical_pdf_and_settings_reuse_extraction_without_reusing_reviews(stores):
    import yaml

    jobs, results, _ = stores
    first, claimed = start_extraction(jobs)
    sections = [{'msds_index': 0, 'section': no, 'title': str(no), 'pages': [1]}
                for no in (1, 2, 3, 8, 9, 11, 12, 14, 15)]
    checks = {'sections': [{**{k: row[k] for k in ('msds_index', 'section')}, 'ok': True,
                            'errors': [], 'reextracted': False} for row in sections],
              'schema_errors': [], 'to21_validator': [], 'needs_review': [], 'warnings': []}
    doc = {'doc': {'doc_id': first['id'], 'source_file': 'one.pdf',
                   'extraction': {'extracted_at': '2026-11-03T12:00:00+09:00'}},
           'msds': [{}]}
    jobs.bind(first['id'], claimed['lease_token']).apply(first['id'],
        {'type': 'plan', 'msds_count': 1, 'page_count': 1, 'sections': sections})
    for row in sections:
        jobs.bind(first['id'], claimed['lease_token']).apply(first['id'],
            {'type': 'section_done', 'msds_index': 0, 'section': row['section'], 'ok': True,
             'needs_review': False, 'reextracted': False, 'errors': []})
    results.save_for_lease(first['id'], claimed['lease_token'], doc, checks,
                           extracted_at='2026-11-03T12:00:00+09:00')
    finish(jobs, first, claimed)
    info = {'model_tag': 'model', 'model_config_sha256': 'a' * 64, 'prompt_hashes': {},
            'schema_version': 'v0.6', 'dictionary_version': 'v0.6', 'git_commit': 'abc123',
            'rows_sections': [], 'rows_max_tokens': None, 'image_input': False}
    old_run = jobs.attempt_paths(first['id'], claimed['lease_token'])['runs_dir'] / first['id']
    old_run.mkdir(parents=True)
    (old_run / 'run_info.yaml').write_text(yaml.safe_dump(info), encoding='utf-8')
    for row in sections:
        raw = old_run / 'raw' / f"{first['id']}_m0_s{row['section']:02d}.json"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(json.dumps({'doc_id': first['id'], 'msds_index': 0,
                                   'section': row['section']}), encoding='utf-8')
    jobs.update_review(first['id'], lambda record: review.set_field(
        record, {'msds': [{'product': {'name': '원본'}}]}, 0, 'product.name',
        'edit', '수정', '검토자', '2026-11-03T13:00:00+09:00'))
    second, claim = start_extraction(jobs)
    assert first['id'] in second['duplicate_of']

    def save_info(path, tag, pages_dir):
        path.mkdir(parents=True, exist_ok=True)
        (path / 'run_info.yaml').write_text(yaml.safe_dump(info), encoding='utf-8')

    steps = SimpleNamespace(save_run_info=save_info,
                            extract=lambda *args, **kwargs: pytest.fail('model extraction must be skipped'))
    worker = PostgresWorker(jobs, steps=steps, result_store=results)
    worker._extract(jobs.bind(second['id'], claim['lease_token']), second['id'],
                    jobs.attempt_paths(second['id'], claim['lease_token']), claim['lease_token'])
    jobs.complete(second['id'], claim['lease_token'])
    assert jobs.get(second['id'])['reused_from'] == first['id']
    assert results.get_active(second['id'])['extraction']['doc']['doc_id'] == second['id']
    assert jobs.load_review(second['id']) == review.empty()
    no_reuse = jobs.create(b'%PDF-1.7\nfake', 'one.pdf', None, 'model',
                           today='20261103', reuse=False)
    assert worker._reuse_completed(jobs, no_reuse,
        {'runs_dir': jobs.root / 'unused'}, lambda event: None) is None


def test_atomic_pair_is_idempotent_and_visible_only_after_completion(stores):
    jobs, results, _ = stores
    job, claim = start_extraction(jobs)
    pdf_json = {'doc': {'doc_id': job['id']}, 'msds': [{'product': {'name': '시험'}}]}
    check_json = {'schema_errors': [], 'to21_validator': [{'level': '오류', 'rule': 'V22'}]}
    one = results.save_for_lease(job['id'], claim['lease_token'], pdf_json, check_json)
    assert results.save_for_lease(job['id'], claim['lease_token'], pdf_json, check_json) == one
    with pytest.raises(ResultNotReady):
        results.get_active(job['id'])
    finish(jobs, job, claim)
    saved = results.get_active(job['id'])
    assert saved['extraction'] == pdf_json and saved['checks'] == check_json
    assert saved['extraction_sha256'] == canonical_sha256(pdf_json)
    assert results.save_completed(job['id'], claim['lease_token'], pdf_json, check_json) == one


def test_completed_attempt_timestamp_is_preserved_and_may_be_backfilled(stores):
    jobs, results, _ = stores
    job, claim = start_extraction(jobs)
    observed = '2026-11-03T09:20:00+09:00'
    results.save_for_lease(job['id'], claim['lease_token'], {'v': 1}, {}, extracted_at=observed)
    finish(jobs, job, claim)
    result = results.get_active(job['id'])
    assert result['extracted_at'] == observed and result['extracted_at_source'] == 'worker'
    assert results.save_completed(job['id'], claim['lease_token'], {'v': 1}, {})

    another, second = start_extraction(jobs)
    finish(jobs, another, second)
    results.save_completed(another['id'], second['lease_token'], {'v': 2}, {})
    backfilled = results.get_active(another['id'])
    assert backfilled['extracted_at']
    assert backfilled['extracted_at_source'] == 'job_finished_at'


def test_completion_timestamp_without_timezone_is_rejected(stores):
    jobs, results, _ = stores
    job, claim = start_extraction(jobs)
    with pytest.raises(ValueError, match='시간대'):
        results.save_for_lease(job['id'], claim['lease_token'], {}, {}, extracted_at='2026-11-03T00:00:00')


def test_different_payload_cannot_replace_saved_attempt(stores):
    jobs, results, _ = stores
    job, claim = start_extraction(jobs)
    token = claim['lease_token']
    results.save_for_lease(job['id'], token, {'result': 1}, {'errors': []})
    with pytest.raises(ResultConflict):
        results.save_for_lease(job['id'], token, {'result': 2}, {'errors': []})
    with pytest.raises(ResultConflict):
        results.save_for_lease(job['id'], token, {'result': 1}, {'errors': ['changed']})
    finish(jobs, job, claim)
    assert results.get_active(job['id'])['extraction'] == {'result': 1}
    assert results.get_active(job['id'])['checks'] == {'errors': []}


def test_expired_or_wrong_lease_never_stores_results(stores):
    jobs, results, _ = stores
    job, claim = start_extraction(jobs)
    token = claim['lease_token']
    with pytest.raises(LeaseLost):
        results.save_for_lease(job['id'], uuid.uuid4().hex, {'result': 1}, {})
    with jobs._connect() as db:
        db.execute(sql.SQL("UPDATE {} SET lease_expires_at=now()-interval '1 second' WHERE job_id=%s")
                   .format(jobs.table), (job['id'],))
    with pytest.raises(LeaseLost):
        results.save_for_lease(job['id'], token, {'result': 1}, {})
    with jobs._connect() as db:
        assert db.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(results.results)).fetchone()['n'] == 0


def test_restart_does_not_publish_old_attempt_and_preserves_history(stores):
    jobs, results, _ = stores
    job, claim = start_extraction(jobs)
    token = claim['lease_token']
    results.save_for_lease(job['id'], token, {'result': 'old'}, {})
    with jobs._connect() as db:
        db.execute(sql.SQL("UPDATE {} SET lease_expires_at=now()-interval '1 second' WHERE job_id=%s")
                   .format(jobs.table), (job['id'],))
    assert jobs.recover_expired() == 1
    with pytest.raises(ResultNotReady):
        results.get_active(job['id'])
    with pytest.raises(LeaseLost):
        results.save_for_lease(job['id'], token, {'result': 'old'}, {})
    pre = jobs.claim('preprocess')
    jobs.queue_next(job['id'], pre['lease_token'])
    next_claim = jobs.claim('extract')
    results.save_for_lease(job['id'], next_claim['lease_token'], {'result': 'new'}, {})
    finish(jobs, job, next_claim)
    assert results.get_active(job['id'])['extraction'] == {'result': 'new'}
    with jobs._connect() as db:
        assert db.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(results.results)).fetchone()['n'] == 4
    with pytest.raises(ResultNotReady):
        results.save_completed(job['id'], token, {'result': 'old'}, {})


def test_concurrent_identical_saves_create_one_pair(stores):
    jobs, results, _ = stores
    job, claim = start_extraction(jobs)
    with ThreadPoolExecutor(max_workers=2) as pool:
        saved = list(pool.map(lambda _: results.save_for_lease(job['id'], claim['lease_token'], {'v': 1}, {}), range(2)))
    assert saved[0] == saved[1]
    with jobs._connect() as db:
        assert db.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(results.results)).fetchone()['n'] == 2


def test_second_row_failure_rolls_back_first(stores):
    jobs, results, schema = stores
    job, claim = start_extraction(jobs)
    with jobs._connect() as db:
        db.execute(sql.SQL("""CREATE FUNCTION {}.reject_check() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.kind='extraction_check' THEN RAISE EXCEPTION 'test'; END IF; RETURN NEW; END $$""")
            .format(sql.Identifier(schema)))
        db.execute(sql.SQL("CREATE TRIGGER fail_check BEFORE INSERT ON {} FOR EACH ROW EXECUTE FUNCTION {}.reject_check()")
                   .format(results.results, sql.Identifier(schema)))
    with pytest.raises(psycopg.Error):
        results.save_for_lease(job['id'], claim['lease_token'], {'result': 1}, {})
    with jobs._connect() as db:
        assert db.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(results.results)).fetchone()['n'] == 0


def test_lease_expiring_during_database_write_rolls_back_pair(stores):
    jobs, results, schema = stores
    job, claim = start_extraction(jobs)
    with jobs._connect() as db:
        db.execute(sql.SQL("""CREATE FUNCTION {}.delay_check() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.kind='extraction_check' THEN PERFORM pg_sleep(0.5); END IF; RETURN NEW; END $$""")
            .format(sql.Identifier(schema)))
        db.execute(sql.SQL("CREATE TRIGGER delay_check BEFORE INSERT ON {} FOR EACH ROW EXECUTE FUNCTION {}.delay_check()")
                   .format(results.results, sql.Identifier(schema)))
        db.execute(sql.SQL("UPDATE {} SET lease_expires_at=clock_timestamp()+interval '0.2 second' WHERE job_id=%s")
                   .format(jobs.table), (job['id'],))
    with pytest.raises(LeaseLost):
        results.save_for_lease(job['id'], claim['lease_token'], {'result': 1}, {})
    with jobs._connect() as db:
        assert db.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(results.results)).fetchone()['n'] == 0


def test_completed_result_api_persists_existing_output_and_reports_errors(stores, monkeypatch):
    from msds.api import extract_app

    jobs, results, _ = stores
    job, claim = start_extraction(jobs)
    finish(jobs, job, claim)
    run = jobs.attempt_paths(job['id'], claim['lease_token'])['runs_dir'] / job['id']
    out = run / 'outputs' / f"{job['id']}.json"
    checks = run / 'checks' / f"{job['id']}.json"
    out.parent.mkdir(parents=True)
    checks.parent.mkdir(parents=True)
    doc = {'doc': {'doc_id': job['id'], 'extraction': {'extracted_at': '2026-11-03T09:30:00+09:00'}},
           'msds': []}
    review_checks = {'schema_errors': [], 'to21_validator': [{'level': '오류', 'rule': 'V22', 'field': None}],
                     'sections': [], 'needs_review': []}
    out.write_text(json.dumps(doc), encoding='utf-8')
    checks.write_text(json.dumps(review_checks, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(extract_app, 'validate_document', lambda doc, checks: (dict(checks), {}))
    app = extract_app.create_app(store=jobs, static_dir=None)
    app.state.store = jobs
    client = TestClient(app)
    try:
        response = client.post(f"/api/documents/{job['id']}/results/persist")
        assert response.status_code == 200
        assert response.json()['validation']['status'] == 'invalid'
        assert response.json()['validation']['validator_errors'] == 1
        assert client.post(f"/api/documents/{job['id']}/results/persist").status_code == 200
        assert client.get(f"/api/documents/{job['id']}/result").json()['validation']['status'] == 'invalid'
        stored = client.get(f"/api/documents/{job['id']}/results/stored")
        assert stored.status_code == 200
        assert stored.json()['validation']['validator_errors'] == 1
        assert stored.json()['to21'] == doc
        monkeypatch.setattr(extract_app, 'validate_document',
                            lambda doc, checks: ({**checks, 'schema_errors': ['changed']}, {}))
        assert client.post(f"/api/documents/{job['id']}/results/persist").status_code == 409
    finally:
        client.close()
    saved = results.get_active(job['id'])
    assert saved['checks'] == review_checks
    assert saved['extracted_at'] == '2026-11-03T09:30:00+09:00'


@pytest.mark.parametrize('auto_handoff', ['off', 'success', 'failure'])
def test_worker_persists_results_and_exposes_invalid_verification(stores, monkeypatch, auto_handoff):
    from msds.service.worker import PostgresWorker
    from msds.service import handoff

    jobs, results, _ = stores
    published = []
    if auto_handoff == 'off':
        monkeypatch.delenv('MSDS_AUTO_HANDOFF', raising=False)
    else:
        monkeypatch.setenv('MSDS_AUTO_HANDOFF', '1')

        def publish(store, job_id, *, as_of, schema):
            if auto_handoff == 'failure':
                raise RuntimeError('handoff unavailable')
            published.append((job_id, as_of, schema))

        monkeypatch.setattr(handoff, 'publish_handoff', publish)
    job = jobs.create(b'%PDF-1.7\ntest', 'one.pdf', None, 'model', today='20261103')

    def preprocess(path, doc_id, *, force, on_page, pages_root):
        (pages_root / doc_id).mkdir(parents=True)
        on_page(1, 1)
        return {'page_count': 1, 'text_layer': '정상'}

    def extract(doc_id, model_tag, run_name, *, pages_dir, sections_dir, runs_dir, on_event):
        run = runs_dir / doc_id
        (run / 'outputs').mkdir(parents=True)
        (run / 'checks').mkdir(parents=True)
        doc = {'doc': {'doc_id': doc_id, 'extraction': {'extracted_at': '2026-11-03T09:30:00+09:00'}},
               'msds': [{'extras': [{'section_no': 3}]}]}
        checks = {'schema_errors': [], 'to21_validator': [{'level': '오류', 'rule': 'V22',
                                                            'field': 'msds[0].extras[0]'}],
                  'sections': [], 'needs_review': []}
        (run / 'outputs' / f'{doc_id}.json').write_text(json.dumps(doc), encoding='utf-8')
        (run / 'checks' / f'{doc_id}.json').write_text(json.dumps(checks, ensure_ascii=False), encoding='utf-8')
        return {'sections_ok': 1}

    steps = SimpleNamespace(preprocess=preprocess, sections=lambda *args: None,
                            save_run_info=lambda *args: None, extract=extract)
    worker = PostgresWorker(jobs, steps=steps, result_store=results, poll_seconds=.01, lease_seconds=5)
    try:
        worker.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = jobs.get(job['id'])['status']
            if (auto_handoff == 'off' and status in ('done', 'failed')
                    or auto_handoff == 'success' and published
                    or auto_handoff == 'failure' and status == 'failed'):
                break
            time.sleep(.02)
        state = jobs.get(job['id'])
        assert state['status'] == ('failed' if auto_handoff == 'failure' else 'done')
        assert state['summary']['validation']['status'] == 'invalid'
        assert state['summary']['validation']['validator_errors'] == 1
        assert state['summary']['results_persisted'] is True
        if auto_handoff == 'failure':
            assert '자동 판정 전달 실패' in state['error']
        else:
            assert results.get_active(job['id'])['extracted_at'] == '2026-11-03T09:30:00+09:00'
        if auto_handoff == 'success':
            assert published == [(job['id'], '2026-11-03', jobs.schema)]
    finally:
        worker.stop(timeout=5)
