"""Publish immutable, evidence-backed A-to-B handoff records.

The handoff is built from a saved A2 result and its actual run metadata.  No
missing provenance, date or validation result is invented.  Publishing is
serialized with retry and review by locking the same PostgreSQL job row.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from psycopg import sql
from psycopg.types.json import Jsonb
from referencing import Registry, Resource

from msds.checks.source_match import match
from msds.checks.validator import run_to21_validator
from msds.common import paths
from msds.common.merge import now_kst
from msds.common.schema import validate_to21
from msds.extract.section_runner import raw_path
from msds.preprocess.render import load_pages, match_pages
from msds.service import review
from msds.service.results import ResultNotReady, ResultStore, canonical_sha256

_REASONS = {'extraction_done', 'values_reviewed', 'value_edited', 'rerun'}
_SECTIONS = {1, 2, 3, 8, 9, 11, 12, 14, 15}
_VALIDATOR_PATH = re.compile(r'^msds\[(\d+)\](?:\.|\[|$)')
_SHA256 = re.compile(r'^[0-9a-f]{64}$')
_COMMIT = re.compile(r'^[0-9a-f]{7,40}$')
_KST = timezone(timedelta(hours=9))


class HandoffNotReady(RuntimeError):
    """A handoff cannot be published without the required evidence."""


def _read_json(path: Path, description: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise HandoffNotReady(f'{description}을 읽을 수 없습니다') from exc
    if not isinstance(value, dict):
        raise HandoffNotReady(f'{description}은 JSON 객체여야 합니다')
    return value


def validate_contract(payload: dict, *, contract_dir: Path | None = None,
                      extraction_schema_path: Path | None = None) -> None:
    """Validate both handoff/1 and the externally supplied TO21 schema offline."""
    directory = Path(contract_dir or paths.ROOT / 'docs' / 'contracts')
    contract = _read_json(directory / '1-handoff.schema.json', 'handoff 계약')
    common = _read_json(directory / 'common.schema.json', '공통 계약')
    try:
        schema_path = Path(extraction_schema_path) if extraction_schema_path else paths.to21_file('schema')
    except FileNotFoundError as exc:
        raise HandoffNotReady('TO21 추출 스키마가 필요합니다') from exc
    extraction_schema = _read_json(schema_path, 'TO21 추출 스키마')
    try:
        resources = [common, extraction_schema]
        if any(not isinstance(item.get('$id'), str) for item in resources):
            raise ValueError('스키마 식별자 누락')
        registry = Registry().with_resources((item['$id'], Resource.from_contents(item)) for item in resources)
        Draft202012Validator.check_schema(contract)
        validator = Draft202012Validator(contract, registry=registry, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(payload), key=lambda error: tuple(map(str, error.absolute_path)))
    except Exception as exc:
        raise HandoffNotReady('handoff 계약을 검증할 수 없습니다') from exc
    if errors:
        # Report paths, never the extracted values or the full document.
        locations = ['.'.join(map(str, error.absolute_path)) or '(root)' for error in errors[:8]]
        raise HandoffNotReady('handoff 계약 불일치: ' + ', '.join(locations))


def extraction_date(extracted_at: str) -> str:
    """Use the recorded, timezone-aware completion time in the user's KST."""
    try:
        stamp = datetime.fromisoformat(extracted_at)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError('시간대 누락')
    except (TypeError, ValueError) as exc:
        raise HandoffNotReady('실제 추출 완료 시각이 없습니다') from exc
    return stamp.astimezone(_KST).date().isoformat()


def _record_validation(extraction: dict, checks: dict) -> tuple[int, int]:
    """Attach the real validator output without modifying the saved source."""
    rows = checks.get('to21_validator')
    if not isinstance(rows, list) or not isinstance(extraction.get('msds'), list):
        raise HandoffNotReady('TO21 검증 결과가 없습니다')
    if not isinstance(checks.get('schema_errors'), list) or checks['schema_errors']:
        raise HandoffNotReady('추출 JSON 스키마 오류가 있어 전달할 수 없습니다')
    for record in rows:
        if not isinstance(record, dict) or record.get('level') not in ('오류', '경고'):
            raise HandoffNotReady('검증기 예외 또는 알 수 없는 검증 결과가 있습니다')
        field = record.get('field')
        match_index = _VALIDATOR_PATH.match(field) if isinstance(field, str) else None
        if not match_index or int(match_index.group(1)) >= len(extraction['msds']):
            raise HandoffNotReady('검증 결과의 MSDS 위치를 확인할 수 없습니다')
        item = extraction['msds'][int(match_index.group(1))]
        if not isinstance(item, dict) or not isinstance(item.get('validation'), list):
            raise HandoffNotReady('추출 결과의 검증 기록이 올바르지 않습니다')
        new = {**{k: record.get(k) for k in ('rule', 'level', 'field', 'message')},
               'review_status': '미검토', 'review_note': None}
        if not any(all(existing.get(k) == new[k] for k in ('rule', 'level', 'field', 'message'))
                   for existing in item['validation'] if isinstance(existing, dict)):
            item['validation'].append(new)
    all_rows = [row for item in extraction['msds'] for row in item.get('validation', [])]
    if any(not isinstance(row, dict) or row.get('level') not in ('오류', '경고') for row in all_rows):
        raise HandoffNotReady('기존 검증 기록의 수준을 확인할 수 없습니다')
    return (sum(row['level'] == '오류' for row in all_rows),
            sum(row['level'] == '경고' for row in all_rows))


def _field_status(record: dict) -> list[dict]:
    fields = record.get('fields')
    if not isinstance(fields, dict):
        raise HandoffNotReady('검수 기록의 칸 상태가 올바르지 않습니다')
    result = []
    for key, value in sorted(fields.items()):
        if not isinstance(key, str) or not isinstance(value, dict):
            raise HandoffNotReady('검수 기록의 칸 상태가 올바르지 않습니다')
        index, sep, field = key.partition(':')
        status = {'confirmed': '확인함', 'edited': '수정됨'}.get(value.get('state'))
        if not sep or not index.isdecimal() or not field or status is None:
            raise HandoffNotReady('검수 기록의 칸 상태를 해석할 수 없습니다')
        result.append({'msds_index': int(index), 'field': field, 'status': status})
    return result


def _section_checks(checks: dict, run_dir: Path, job_id: str, msds_count: int) -> tuple[list[dict], list[dict]]:
    sections = checks.get('sections')
    if not isinstance(sections, list) or not sections:
        raise HandoffNotReady('항목별 추출 검사 기록이 없습니다')
    failed, reextracted, seen = [], [], set()
    for row in sections:
        if not isinstance(row, dict):
            raise HandoffNotReady('항목별 추출 검사 기록이 올바르지 않습니다')
        index, section, ok = row.get('msds_index'), row.get('section'), row.get('ok')
        if (not isinstance(index, int) or isinstance(index, bool) or index < 0 or
                section not in _SECTIONS or not isinstance(ok, bool) or (index, section) in seen):
            raise HandoffNotReady('항목별 추출 검사 기록이 올바르지 않습니다')
        seen.add((index, section))
        raw = _read_json(raw_path(run_dir, job_id, index, section), '항목별 원본 실행 기록')
        if raw.get('msds_index') != index or raw.get('section') != section:
            raise HandoffNotReady('항목별 원본 실행 기록이 일치하지 않습니다')
        if not ok:
            errors = row.get('errors')
            if not isinstance(errors, list) or not errors:
                raise HandoffNotReady('실패한 항의 오류 기록이 없습니다')
            failed.append({'msds_index': index, 'section': section, 'error': '; '.join(map(str, errors))})
        if 'first_attempt' in raw or 'reextract_attempt' in raw:
            reextracted.append({'msds_index': index, 'section': section})
    expected = {(index, section) for index in range(msds_count) for section in _SECTIONS}
    if not expected or seen != expected:
        raise HandoffNotReady('각 MSDS의 9개 추출 항목 기록이 완전하지 않습니다')
    return failed, reextracted


def _source_mismatch(extraction: dict, *, job_id: str, pages_dir: Path) -> list[dict]:
    try:
        texts, states = match_pages(load_pages(job_id, pages_root=pages_dir)['pages'])
    except (KeyError, OSError, ValueError) as exc:
        raise HandoffNotReady('원문 대조에 필요한 전처리 자료가 없습니다') from exc
    bad = set()
    for index, item in enumerate(extraction['msds']):
        evidence = item.get('evidence')
        if not isinstance(evidence, list):
            raise HandoffNotReady('추출 근거 목록이 없습니다')
        for row in evidence:
            if not isinstance(row, dict) or not isinstance(row.get('field'), str) or not row['field']:
                raise HandoffNotReady('추출 근거의 필드 경로가 없습니다')
            result = match(row.get('source_text'), row.get('page'), texts, states)
            if result['result'] == '불일치':
                bad.add((index, row['field']))
    return [{'msds_index': index, 'field': field} for index, field in sorted(bad)]


def build_handoff(*, job_id: str, handoff_seq: int, reason: str, created_at: str,
                  as_of: str, state: dict, extraction: dict, checks: dict,
                  review_record: dict, run_info: dict, extracted_at: str,
                  run_dir: Path, pages_dir: Path) -> dict:
    """Build a handoff solely from saved evidence; leave all source objects unchanged."""
    if reason not in _REASONS:
        raise HandoffNotReady('허용되지 않은 전달 사유입니다')
    if not isinstance(extraction, dict) or not isinstance(checks, dict) or not isinstance(run_info, dict):
        raise HandoffNotReady('저장된 추출 자료가 올바르지 않습니다')
    doc = extraction.get('doc')
    extraction_metadata = doc.get('extraction') if isinstance(doc, dict) else None
    doc_extracted_at = extraction_metadata.get('extracted_at') if isinstance(extraction_metadata, dict) else None
    actual_date = extraction_date(doc_extracted_at)
    if extraction_date(extracted_at) != actual_date:
        raise HandoffNotReady('추출 결과와 저장 기록의 실제 추출 날짜가 다릅니다')
    if as_of != actual_date:
        raise HandoffNotReady('기준일은 결과에 기록된 실제 추출 날짜여야 합니다')
    requested_date = state.get('as_of') if isinstance(state, dict) else None
    if requested_date is not None and requested_date != actual_date:
        raise HandoffNotReady('업로드 기준일과 실제 추출 날짜가 달라 전달할 수 없습니다')
    cfg_hash, commit = run_info.get('model_config_sha256'), run_info.get('git_commit')
    if not isinstance(cfg_hash, str) or not _SHA256.fullmatch(cfg_hash):
        raise HandoffNotReady('실제 실행의 모델 설정 해시가 없습니다')
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        raise HandoffNotReady('실제 실행의 코드 버전이 없습니다')
    if run_info.get('model_tag') != state.get('model_tag'):
        raise HandoffNotReady('실제 실행의 모델 설정이 작업 기록과 다릅니다')
    if not isinstance(doc, dict) or run_info.get('schema_version') != doc.get('schema_version'):
        raise HandoffNotReady('실제 실행의 스키마 버전이 다르거나 없습니다')
    if doc.get('schema_version') != 'TO21-MSDS-EXT v0.6' or doc.get('dictionary_version') != 'v0.6':
        raise HandoffNotReady('지원하지 않는 스키마 또는 사전 버전입니다')
    if doc.get('doc_id') != job_id:
        raise HandoffNotReady('추출 결과와 작업 번호가 다릅니다')
    try:
        edited = review.apply_edits(extraction, review_record)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise HandoffNotReady('검수 수정 기록을 적용할 수 없습니다') from exc
    checks_for_handoff = copy.deepcopy(checks)
    fields = review_record.get('fields')
    if not isinstance(fields, dict):
        raise HandoffNotReady('검수 기록의 칸 상태가 올바르지 않습니다')
    if any(isinstance(value, dict) and value.get('state') == 'edited' for value in fields.values()):
        try:
            checks_for_handoff['schema_errors'] = validate_to21(edited)
            checks_for_handoff['to21_validator'] = run_to21_validator(edited)
        except Exception as exc:
            raise HandoffNotReady('수정한 추출값을 다시 검증할 수 없습니다') from exc
    errors, warnings = _record_validation(edited, checks_for_handoff)
    failed, retried = _section_checks(checks, run_dir, job_id, len(edited['msds']))
    # The review view selects fields from the original, then overlays edits.
    # A field cleared by review must still count toward the reviewable total.
    fields_total = review.build_view(extraction, checks, state.get('sections', []),
                                    review_record)['summary']['fields_total']
    payload = {
        'contract': 'handoff/1', 'job_id': job_id, 'handoff_seq': handoff_seq,
        'reason': reason, 'created_at': created_at, 'as_of': as_of,
        'source': {'filename': state.get('filename'), 'file_sha256': state.get('sha256'),
                   'page_count': state.get('page_count'), 'text_layer': state.get('text_layer')},
        'extraction_settings': {'model_tag': state.get('model_tag'), 'model_config_sha256': cfg_hash,
                                'code_commit': commit, 'schema_version': doc['schema_version'],
                                'dictionary_version': doc['dictionary_version'], 'reused_from': None},
        'extraction': edited, 'extraction_sha256': canonical_sha256(edited),
        'checks': {'validator': {'version': 'v0.6', 'errors': errors, 'warnings': warnings},
                   'failed_sections': failed, 'reextracted_sections': retried,
                   'source_mismatch': _source_mismatch(edited, job_id=job_id, pages_dir=pages_dir)},
        'field_status': _field_status(review_record),
        'fields_total': fields_total,
    }
    validate_contract(payload)
    return payload


def publish_handoff(store, job_id: str, *, as_of: str, reason: str = 'extraction_done',
                    schema: str = 'extract') -> dict[str, Any]:
    """Publish a new immutable sequence for the current completed DB result."""
    saved = ResultStore(store.dsn, schema=schema).get_active(job_id)
    token = saved.get('attempt_token')
    extracted_at = saved.get('extracted_at')
    if not extracted_at or saved.get('extracted_at_source') not in ('worker', 'job_finished_at'):
        raise HandoffNotReady('실제 추출 완료 시각 기록이 없습니다')
    artifact = store.attempt_paths(job_id, token)
    run_dir = artifact['runs_dir'] / job_id
    try:
        run_info = yaml.safe_load((run_dir / 'run_info.yaml').read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as exc:
        raise HandoffNotReady('실제 모델 실행 설정 기록이 없습니다') from exc
    with store._connect() as db:
        job = db.execute(sql.SQL('SELECT status, progress_json FROM {} WHERE job_id=%s FOR UPDATE')
                         .format(store.table), (job_id,)).fetchone()
        if not job or job['status'] != 'done' or job['progress_json'].get('_active_token') != token:
            raise ResultNotReady('추출 결과가 변경되어 전달할 수 없습니다')
        state = job['progress_json']
        path = store._review_path(job_id, state)
        record = _read_json(path, '검수 기록') if path.is_file() else review.empty()
        row = db.execute(sql.SQL('SELECT COALESCE(max(handoff_seq), 0) AS seq FROM {} WHERE job_id=%s')
                         .format(sql.Identifier(schema, 'handoff')), (job_id,)).fetchone()
        sequence = row['seq'] + 1
        payload = build_handoff(job_id=job_id, handoff_seq=sequence, reason=reason, created_at=now_kst(),
                                as_of=as_of, state=state, extraction=saved['extraction'], checks=saved['checks'],
                                review_record=record, run_info=run_info, extracted_at=extracted_at,
                                run_dir=run_dir, pages_dir=artifact['pages_dir'])
        db.execute(sql.SQL('''INSERT INTO {} (job_id, handoff_seq, reason, as_of, extraction_sha256,
            payload_json, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)''').format(sql.Identifier(schema, 'handoff')),
            (job_id, sequence, reason, as_of, payload['extraction_sha256'], Jsonb(payload), payload['created_at']))
    return payload
