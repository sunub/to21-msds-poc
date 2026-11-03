"""Handoff contracts preserve evidence, checks, and reviewed values."""
from __future__ import annotations

import copy
import json
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from msds.service import handoff, review
from msds.service.jobs import PostgresJobStore
from msds.service.results import ResultStore, canonical_sha256


@pytest.fixture
def sample(tmp_path, monkeypatch):
    fake_schema = tmp_path / 'to21.json'
    fake_schema.write_text(json.dumps({
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'https://to21.co.kr/schema/msds-extraction/v0.6', 'type': 'object',
    }), encoding='utf-8')
    original_validate = handoff.validate_contract
    monkeypatch.setattr(handoff, 'validate_contract', lambda value: original_validate(
        value, extraction_schema_path=fake_schema))
    monkeypatch.setattr(handoff, 'load_pages', lambda job_id, pages_root: {'pages': [{
        'page': 1, 'match_text': '원본에서 확인된 근거', 'state': '정상', 'source': '텍스트층',
    }]})
    job_id = 'U-20261103-001'
    run = tmp_path / 'run'
    for section in sorted(handoff._SECTIONS):
        retry = section == 2
        raw = handoff.raw_path(run, job_id, 0, section)
        raw.parent.mkdir(parents=True, exist_ok=True)
        record = {'doc_id': job_id, 'msds_index': 0, 'section': section}
        if retry:
            record['reextract_attempt'] = {'ok': False}
        raw.write_text(json.dumps(record), encoding='utf-8')
    doc = {'doc': {'doc_id': job_id, 'schema_version': 'TO21-MSDS-EXT v0.6', 'dictionary_version': 'v0.6'},
           'msds': [{'product': {'name': '원본'}, 'validation': [], 'evidence': [
               {'field': 'product.name', 'page': 1, 'source_text': '확인된 근거'},
               {'field': 'hazard.signal_word', 'page': 1, 'source_text': '존재하지않는내용'},
           ]}]}
    checks = {'schema_errors': [], 'to21_validator': [
        {'rule': 'V22', 'level': '오류', 'field': 'msds[0].product.name', 'message': '값 확인'},
        {'rule': 'V14', 'level': '경고', 'field': 'msds[0].evidence', 'message': '근거 확인'},
    ], 'sections': [
        {'msds_index': 0, 'section': section, 'ok': section != 2,
         'errors': ['응답 실패'] if section == 2 else []}
        for section in sorted(handoff._SECTIONS)
    ]}
    state = {'filename': 'test.pdf', 'sha256': 'b' * 64, 'page_count': 1,
             'text_layer': '정상', 'model_tag': 'test'}
    return {'job_id': job_id, 'handoff_seq': 1, 'reason': 'extraction_done',
            'created_at': '2026-11-03T10:00:00+09:00', 'as_of': '2026-11-03',
            'state': state, 'extraction': doc, 'checks': checks, 'review_record': review.empty(),
            'run_info': {'model_tag': 'test', 'model_config_sha256': 'a' * 64,
                         'git_commit': 'a1b2c3d', 'schema_version': 'TO21-MSDS-EXT v0.6'},
            'extracted_at': '2026-11-03T10:00:00+09:00', 'run_dir': run, 'pages_dir': tmp_path}


def test_contract_preserves_validator_errors_failed_sections_and_real_retry(sample):
    original = copy.deepcopy(sample['extraction'])
    payload = handoff.build_handoff(**sample)
    assert payload['checks']['validator'] == {'version': 'v0.6', 'errors': 1, 'warnings': 1}
    assert payload['checks']['failed_sections'] == [{'msds_index': 0, 'section': 2, 'error': '응답 실패'}]
    assert payload['checks']['reextracted_sections'] == [{'msds_index': 0, 'section': 2}]
    assert payload['checks']['source_mismatch'] == [{'msds_index': 0, 'field': 'hazard.signal_word'}]
    assert len(payload['extraction']['msds'][0]['validation']) == 2
    assert payload['extraction_sha256'] == canonical_sha256(payload['extraction'])
    assert sample['extraction'] == original


def test_extraction_date_uses_recorded_timestamp_in_korean_time():
    assert handoff.extraction_date('2026-11-02T16:00:00+00:00') == '2026-11-03'
    with pytest.raises(handoff.HandoffNotReady):
        handoff.extraction_date('2026-11-03T00:00:00')


@pytest.mark.parametrize('change', ['missing_hash', 'missing_commit', 'wrong_model', 'wrong_date',
                                    'validator_exception', 'schema_errors', 'missing_raw',
                                    'missing_section', 'duplicate_section', 'wrong_index'])
def test_missing_or_inconsistent_evidence_is_rejected(sample, change):
    if change == 'missing_hash':
        sample['run_info'].pop('model_config_sha256')
    elif change == 'missing_commit':
        sample['run_info']['git_commit'] = None
    elif change == 'wrong_model':
        sample['run_info']['model_tag'] = 'other'
    elif change == 'wrong_date':
        sample['as_of'] = '2026-11-04'
    elif change == 'validator_exception':
        sample['checks']['to21_validator'][0]['level'] = '예외'
    elif change == 'schema_errors':
        sample['checks']['schema_errors'] = ['schema mismatch']
    elif change == 'missing_raw':
        handoff.raw_path(sample['run_dir'], sample['job_id'], 0, 1).unlink()
    elif change == 'missing_section':
        sample['checks']['sections'].pop()
    elif change == 'duplicate_section':
        sample['checks']['sections'].append(dict(sample['checks']['sections'][0]))
    else:
        sample['checks']['sections'][0]['msds_index'] = 1
    with pytest.raises(handoff.HandoffNotReady):
        handoff.build_handoff(**sample)


def test_edit_revalidates_new_value_and_preserves_original(sample, monkeypatch):
    sample['review_record']['fields']['0:product.name'] = {'state': 'edited', 'value': '검수한 값'}
    monkeypatch.setattr(handoff, 'validate_to21', lambda value: [])
    monkeypatch.setattr(handoff, 'run_to21_validator', lambda value: [
        {'rule': 'V14', 'level': '경고', 'field': 'msds[0].evidence', 'message': '다시 검사'}])
    payload = handoff.build_handoff(**sample)
    assert payload['extraction']['msds'][0]['product']['name'] == '검수한 값'
    assert sample['extraction']['msds'][0]['product']['name'] == '원본'
    assert payload['checks']['validator'] == {'version': 'v0.6', 'errors': 0, 'warnings': 1}
    assert payload['field_status'] == [{'msds_index': 0, 'field': 'product.name', 'status': '수정됨'}]


def test_validator_rejects_contract_with_missing_required_field(sample, tmp_path):
    payload = handoff.build_handoff(**sample)
    payload.pop('extraction_sha256')
    with pytest.raises(handoff.HandoffNotReady):
        handoff.validate_contract(payload)


def test_real_database_serializes_handoff_sequence_and_preserves_rows(sample, tmp_path):
    dsn = os.environ.get('MSDS_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('MSDS_TEST_DATABASE_URL이 지정된 임시 PostgreSQL이 필요합니다')
    schema = 'test_a2_' + uuid.uuid4().hex
    migrations = Path(__file__).resolve().parents[1] / 'migrations'
    files = ['a1_0001_extract_jobs.sql', 'a2_0002_extract_results_reviews_artifacts.sql',
             'a2_0003_extract_handoff.sql']
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        for name in files:
            ddl = (migrations / name).read_text(encoding='utf-8').replace('extract.', f'"{schema}".')
            db.execute(ddl)
    try:
        store = PostgresJobStore(dsn, tmp_path / 'service', schema=schema)
        state = store.create(b'%PDF-1.7\ntest', 'test.pdf', None, 'test', today='20261103')
        job_id = state['id']
        pre = store.claim()
        store.apply(job_id, {'type': 'preprocess_done', 'page_count': 1, 'text_layer': '정상'},
                    lease_token=pre['lease_token'])
        store.queue_next(job_id, pre['lease_token'])
        extracted = store.claim(stage='extract')
        token = extracted['lease_token']
        store.apply(job_id, {'type': 'done', 'summary': {}}, lease_token=token)
        store.finish(job_id, token)
        results = ResultStore(dsn, schema=schema)
        results.save_completed(job_id, token, sample['extraction'], sample['checks'],
                               extracted_at=sample['extracted_at'])
        attempt = store.attempt_paths(job_id, token)
        run = attempt['runs_dir'] / job_id
        shutil.copytree(sample['run_dir'], run)
        import yaml
        (run / 'run_info.yaml').write_text(yaml.safe_dump(sample['run_info']), encoding='utf-8')
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: handoff.publish_handoff(
                store, job_id, as_of=sample['as_of'], schema=schema), range(2)))
        assert sorted(value['handoff_seq'] for value in values) == [1, 2]
        with psycopg.connect(dsn) as db:
            rows = db.execute(sql.SQL('SELECT handoff_seq, extraction_sha256 FROM {} ORDER BY handoff_seq')
                              .format(sql.Identifier(schema, 'handoff'))).fetchall()
            assert len(rows) == 2 and rows[0][1] == rows[1][1]
            with pytest.raises(psycopg.Error) as exc:
                db.execute(sql.SQL('DELETE FROM {}').format(sql.Identifier(schema, 'handoff')))
            assert exc.value.sqlstate == '55000'
    finally:
        with psycopg.connect(dsn, autocommit=True) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
