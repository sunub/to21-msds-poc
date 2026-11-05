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
    doc = {'doc': {'doc_id': job_id, 'schema_version': 'TO21-MSDS-EXT v0.6', 'dictionary_version': 'v0.6',
                   'extraction': {'extracted_at': '2026-11-03T10:00:00+09:00'}},
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
    assert payload['fields_total'] == 1
    assert sample['extraction'] == original


def test_extraction_date_uses_recorded_timestamp_in_korean_time():
    assert handoff.extraction_date('2026-11-02T16:00:00+00:00') == '2026-11-03'
    with pytest.raises(handoff.HandoffNotReady):
        handoff.extraction_date('2026-11-03T00:00:00')


def test_user_supplied_as_of_must_agree_with_actual_extraction_date(sample):
    sample['state']['as_of'] = '2026-11-02'
    with pytest.raises(handoff.HandoffNotReady, match='업로드 기준일'):
        handoff.build_handoff(**sample)
    sample['state']['as_of'] = '2026-11-03'
    assert handoff.build_handoff(**sample)['as_of'] == '2026-11-03'


def test_context_timestamp_cannot_contradict_document_extraction_date(sample):
    sample['extracted_at'] = '2026-11-04T00:00:00+09:00'
    with pytest.raises(handoff.HandoffNotReady, match='저장 기록'):
        handoff.build_handoff(**sample)


def test_document_extraction_timestamp_is_mandatory(sample):
    del sample['extraction']['doc']['extraction']['extracted_at']
    with pytest.raises(handoff.HandoffNotReady, match='시각'):
        handoff.build_handoff(**sample)


def test_timestamp_cross_check_uses_korean_date_not_utc_date(sample):
    sample['extraction']['doc']['extraction']['extracted_at'] = '2026-11-02T16:00:00+00:00'
    sample['extracted_at'] = '2026-11-03T01:05:00+09:00'
    assert handoff.build_handoff(**sample)['as_of'] == '2026-11-03'


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


def test_section_confirmation_marks_its_fields_confirmed(sample, monkeypatch):
    """항 확인을 누르면 그 항의 칸은 확인한 것이다. 검수 화면(build_view)과 같은 기준으로 센다."""
    monkeypatch.setattr(handoff, 'validate_to21', lambda value: [])
    monkeypatch.setattr(handoff, 'run_to21_validator', lambda value: [])
    sample['extraction']['msds'][0]['product'].update(uses=['산업용', '시험용'])
    record = sample['review_record']
    review.set_field(record, sample['extraction'], 0, 'product.uses[0]', 'edit', '고친 용도', 'r', sample['created_at'])
    review.set_section(record, 0, 1, True, 'r', sample['created_at'])
    payload = handoff.build_handoff(**{**sample, 'review_record': record})
    assert payload['field_status'] == [
        {'msds_index': 0, 'field': 'product.name', 'status': '확인함'},
        {'msds_index': 0, 'field': 'product.uses[0]', 'status': '수정됨'},
        {'msds_index': 0, 'field': 'product.uses[1]', 'status': '확인함'},
    ]
    assert payload['fields_total'] == len(payload['field_status']) == 3


def test_fields_total_counts_reviewable_fields_across_msds(sample):
    first = sample['extraction']['msds'][0]
    first['product'].update(name_en='', uses=['산업용', '시험용'])
    first['components'] = [{'cas_no': '123-45-6', 'content': {'lower': 0, 'upper': None},
                            'trade_secret': False, 'seq': 1, 'raw': '원문'}]
    second = {'product': {'name': '두 번째'}, 'validation': [], 'evidence': [],
              'physchem': [{'prop_code': 'PH', 'value': {'value': 0, 'unit': ''}, 'raw': '원문'}],
              'narratives': [{'item_code': 'S04_FIRST_AID', 'value': '대상 항이 아님'}]}
    sample['extraction']['msds'].append(second)
    for section in sorted(handoff._SECTIONS):
        raw = handoff.raw_path(sample['run_dir'], sample['job_id'], 1, section)
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(json.dumps({'msds_index': 1, 'section': section}), encoding='utf-8')
        sample['checks']['sections'].append({'msds_index': 1, 'section': section, 'ok': True})
    payload = handoff.build_handoff(**sample)
    # Six fields in the first MSDS, three in the second. Empty/hidden fields,
    # evidence, validation and unsupported sections do not count.
    assert payload['fields_total'] == 9
    assert payload['field_status'] == []
    view = review.build_view(sample['extraction'], sample['checks'], [], sample['review_record'])
    assert payload['fields_total'] == view['summary']['fields_total']


def test_fields_total_keeps_a_field_cleared_during_review(sample, monkeypatch):
    review.set_field(sample['review_record'], sample['extraction'], 0, 'product.name',
                     'edit', '', 'reviewer', sample['created_at'])
    monkeypatch.setattr(handoff, 'validate_to21', lambda value: [])
    monkeypatch.setattr(handoff, 'run_to21_validator', lambda value: [])
    payload = handoff.build_handoff(**sample)
    assert payload['extraction']['msds'][0]['product']['name'] is None
    assert payload['fields_total'] == len(payload['field_status']) == 1
    view = review.build_view(sample['extraction'], sample['checks'], [], sample['review_record'])
    assert payload['fields_total'] == view['summary']['fields_total']
    assert sample['extraction']['msds'][0]['product']['name'] == '원본'


def test_fields_total_can_be_zero_without_reviewable_values(sample):
    sample['extraction']['msds'][0]['product']['name'] = None
    assert handoff.build_handoff(**sample)['fields_total'] == 0


@pytest.mark.parametrize('field', ['extraction_sha256', 'fields_total'])
def test_validator_rejects_contract_with_missing_required_field(sample, field):
    payload = handoff.build_handoff(**sample)
    payload.pop(field)
    with pytest.raises(handoff.HandoffNotReady):
        handoff.validate_contract(payload)


@pytest.mark.parametrize('value', [-1, 1.5, True, '1', None])
def test_validator_rejects_invalid_fields_total(sample, value):
    payload = handoff.build_handoff(**sample)
    payload['fields_total'] = value
    with pytest.raises(handoff.HandoffNotReady, match='fields_total'):
        handoff.validate_contract(payload)


def test_runtime_handoff_contract_matches_shared_contract():
    root = Path(__file__).resolve().parents[2]
    runtime = json.loads((root / 'docs/contracts/1-handoff.schema.json').read_text(encoding='utf-8'))
    shared = json.loads((root / 'docs/superpowers/specs/contracts/1-handoff.schema.json').read_text(encoding='utf-8'))
    assert runtime == shared


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
        store.update_review(job_id, lambda record: review.set_field(
            record, sample['extraction'], 0, 'product.name', 'confirm', None,
            '검토자', '2026-11-03T12:00:00+09:00'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: handoff.publish_handoff(
                store, job_id, as_of=sample['as_of'], schema=schema), range(2)))
        assert sorted(value['handoff_seq'] for value in values) == [1, 2]
        assert all(value['field_status'] == [
            {'msds_index': 0, 'field': 'product.name', 'status': '확인함'},
        ] for value in values)
        # 검수를 더 하면 넘김을 새로 만든다. 바뀐 것이 없으면 만들지 않는다
        assert handoff.republish_handoff(store, job_id, as_of=sample['as_of'], reason='values_reviewed', schema=schema) is None
        store.update_review(job_id, lambda record: review.set_field(
            record, sample['extraction'], 0, 'product.name', 'reset', None, '검토자', '2026-11-03T12:01:00+09:00'))
        again = handoff.republish_handoff(store, job_id, as_of=sample['as_of'], reason='values_reviewed', schema=schema)
        assert again['handoff_seq'] == 3 and again['field_status'] == []
        # 칸을 하나씩 누르지 않고 항만 확인해도 그 항의 칸은 확인함으로 넘어간다
        store.update_review(job_id, lambda record: review.set_section(record, 0, 1, True, '검토자', '2026-11-03T12:02:00+09:00'))
        last = handoff.republish_handoff(store, job_id, as_of=sample['as_of'], reason='values_reviewed', schema=schema)
        assert last['handoff_seq'] == 4 and last['field_status'] == [{'msds_index': 0, 'field': 'product.name', 'status': '확인함'}]
        assert handoff.republish_handoff(store, job_id, as_of=sample['as_of'], reason='values_reviewed', schema=schema) is None
        with psycopg.connect(dsn) as db:
            rows = db.execute(sql.SQL('SELECT handoff_seq, extraction_sha256, payload_json FROM {} ORDER BY handoff_seq')
                              .format(sql.Identifier(schema, 'handoff'))).fetchall()
            assert len(rows) == 4 and len({row[1] for row in rows}) == 1
            assert all(row[2]['fields_total'] == 1 for row in rows)
            with pytest.raises(psycopg.Error) as exc:
                db.execute(sql.SQL('DELETE FROM {}').format(sql.Identifier(schema, 'handoff')))
            assert exc.value.sqlstate == '55000'
    finally:
        with psycopg.connect(dsn, autocommit=True) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
