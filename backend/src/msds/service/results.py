"""불변 추출 결과와 검사 결과의 원자적 저장.

작업의 현재 임대 또는 완료된 산출물 토큰을 확인해 이전 실행의 결과가 현재
실행에 게시되지 않게 한다. PDF와 원본 산출물 파일은 건드리지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from msds.service.jobs import LeaseLost


class ResultConflict(RuntimeError):
    """같은 실행 토큰으로 다른 내용을 게시하려고 했다."""


class ResultNotReady(RuntimeError):
    """현재 완료된 실행에 해당하는 저장 결과가 없다."""


def canonical_sha256(value: dict) -> str:
    """파트 간 계약의 JSON 정규화 방식으로 해시한다."""
    if not isinstance(value, dict):
        raise ValueError('결과는 JSON 객체여야 합니다')
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def _ids(job_id: str, token: str) -> tuple[str, str]:
    if not re.fullmatch(r'U-\d{8}-\d{3,}', job_id) or not re.fullmatch(r'[0-9a-f]{32}', token):
        raise ValueError('올바르지 않은 작업 번호 또는 실행 토큰입니다')
    prefix = f'a2-{job_id}-{token}'
    return f'{prefix}-extraction', f'{prefix}-check'


def _timestamp(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('추출 완료 시각은 시간대가 포함된 ISO 8601 문자열이어야 합니다')
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('시간대 누락')
    except ValueError as exc:
        raise ValueError('추출 완료 시각은 시간대가 포함된 ISO 8601 문자열이어야 합니다') from exc
    return value


class ResultStore:
    """`extract.results`에 원본 추출·검사 결과를 불변 쌍으로 저장한다."""

    def __init__(self, dsn: str, *, schema: str = 'extract'):
        if not dsn or not dsn.strip():
            raise ValueError('PostgreSQL 접속 설정이 필요합니다')
        if not schema or '\x00' in schema or len(schema.encode('utf-8')) > 63:
            raise ValueError('올바르지 않은 스키마 이름입니다')
        self.dsn = dsn
        self.jobs = sql.Identifier(schema, 'jobs')
        self.results = sql.Identifier(schema, 'results')

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5)

    def validate_schema(self) -> None:
        """기존 DB 테이블을 변경하지 않고 필요한 결과 컬럼을 확인한다."""
        try:
            with self._connect() as db:
                db.execute(sql.SQL("""SELECT result_id, job_id, attempt_no, kind,
                    parent_result_id, payload_json, content_sha256, context_json
                    FROM {} LIMIT 0""").format(self.results))
        except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn) as exc:
            raise RuntimeError('추출 결과 테이블이 없거나 정의가 다릅니다. A2 마이그레이션을 확인하세요') from exc

    def _save(self, job_id: str, token: str, extraction: dict, checks: dict, *, completed: bool,
              extracted_at: str | None) -> dict:
        extraction_id, check_id = _ids(job_id, token)
        extraction_hash, check_hash = canonical_sha256(extraction), canonical_sha256(checks)
        if extracted_at is not None:
            extracted_at = _timestamp(extracted_at)
        with self._connect() as db:
            if completed:
                job = db.execute(sql.SQL("""SELECT attempt_no, attempts_json, progress_json FROM {} WHERE job_id=%s
                    AND status='done' FOR UPDATE""").format(self.jobs), (job_id,)).fetchone()
                if not job or job['progress_json'].get('_active_token') != token:
                    raise ResultNotReady('완료된 현재 실행이 아닙니다')
            else:
                job = db.execute(sql.SQL("""SELECT attempt_no, progress_json FROM {} WHERE job_id=%s
                    AND status='running' AND lease_token=%s AND lease_expires_at>clock_timestamp()
                    AND stage IN ('extract', 'checks', 'finalize')
                    FOR UPDATE""").format(self.jobs), (job_id, token)).fetchone()
                if not job:
                    raise LeaseLost('유효한 작업 임대가 없습니다')
                if job['progress_json'].get('_working_token') != token:
                    raise LeaseLost('현재 추출 실행 토큰이 아닙니다')
            attempt_no = job['attempt_no']
            existing = db.execute(sql.SQL('SELECT context_json FROM {} WHERE result_id=%s')
                                  .format(self.results), (extraction_id,)).fetchone()
            context = {'attempt_token': token}
            if extracted_at is not None:
                context.update(extracted_at=extracted_at, extracted_at_source='worker')
            elif existing:
                # Repeated publication must reuse the original evidence, not a
                # new wall-clock value or a different completion time.
                context = existing['context_json']
                if not isinstance(context, dict) or context.get('attempt_token') != token:
                    raise ResultConflict('저장된 실행 정보가 일치하지 않습니다')
            elif completed:
                attempt = next((a for a in reversed(job['attempts_json'])
                                if a.get('attempt') == attempt_no and a.get('status') == 'done'), None)
                if attempt and attempt.get('finished_at'):
                    context.update(extracted_at=_timestamp(attempt['finished_at']),
                                   extracted_at_source='job_finished_at')
            for result_id, kind, parent, payload, digest in (
                (extraction_id, 'extraction', None, extraction, extraction_hash),
                (check_id, 'extraction_check', extraction_id, checks, check_hash),
            ):
                db.execute(sql.SQL("""INSERT INTO {} (result_id, job_id, attempt_no, kind,
                    parent_result_id, payload_json, content_sha256, context_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (result_id) DO NOTHING""")
                    .format(self.results), (result_id, job_id, attempt_no, kind, parent,
                                            Jsonb(payload), digest, Jsonb(context)))
                saved = db.execute(sql.SQL("""SELECT job_id, attempt_no, kind, parent_result_id,
                    payload_json, content_sha256, context_json FROM {} WHERE result_id=%s""")
                    .format(self.results), (result_id,)).fetchone()
                if (not saved or saved['job_id'] != job_id or saved['attempt_no'] != attempt_no
                        or saved['kind'] != kind or saved['parent_result_id'] != parent
                        or saved['content_sha256'] != digest or saved['context_json'] != context
                        or canonical_sha256(saved['payload_json']) != digest):
                    raise ResultConflict('같은 실행의 저장된 결과와 새 결과가 다릅니다')
            if not completed:
                valid = db.execute(sql.SQL("""SELECT lease_expires_at > clock_timestamp() AS valid
                    FROM {} WHERE job_id=%s AND status='running' AND lease_token=%s""")
                    .format(self.jobs), (job_id, token)).fetchone()
                if not valid or not valid['valid']:
                    raise LeaseLost('결과 저장 중 작업 임대가 만료됐습니다')
        return {'extraction_result_id': extraction_id, 'check_result_id': check_id,
                'extraction_sha256': extraction_hash, 'checks_sha256': check_hash,
                'attempt_no': attempt_no}

    def save_for_lease(self, job_id: str, token: str, extraction: dict, checks: dict, *,
                       extracted_at: str | None = None) -> dict:
        """유효한 작업자 임대에서 저장한다. 임대가 만료되면 전체 롤백된다."""
        return self._save(job_id, token, extraction, checks, completed=False, extracted_at=extracted_at)

    def save_completed(self, job_id: str, token: str, extraction: dict, checks: dict, *,
                       extracted_at: str | None = None) -> dict:
        """완료된 현재 산출물을 안전하게 저장한다 (기존 결과 이관용)."""
        return self._save(job_id, token, extraction, checks, completed=True, extracted_at=extracted_at)

    def get_active(self, job_id: str) -> dict[str, Any]:
        """완료된 현재 실행의 저장된 추출·검사 결과만 반환한다."""
        with self._connect() as db:
            job = db.execute(sql.SQL("""SELECT status, progress_json FROM {} WHERE job_id=%s
                FOR SHARE""").format(self.jobs), (job_id,)).fetchone()
            token = job['progress_json'].get('_active_token') if job and job['status'] == 'done' else None
            if not token:
                raise ResultNotReady('완료된 현재 실행이 없습니다')
            extraction_id, check_id = _ids(job_id, token)
            rows = db.execute(sql.SQL("""SELECT result_id, job_id, kind, parent_result_id,
                payload_json, content_sha256, context_json FROM {} WHERE result_id = ANY(%s)""")
                .format(self.results), ([extraction_id, check_id],)).fetchall()
            by_id = {row['result_id']: row for row in rows}
            if set(by_id) != {extraction_id, check_id}:
                raise ResultNotReady('현재 실행의 결과가 아직 저장되지 않았습니다')
            extraction, checks = by_id[extraction_id], by_id[check_id]
            if (extraction['job_id'] != job_id or extraction['kind'] != 'extraction'
                    or extraction['parent_result_id'] is not None
                    or checks['job_id'] != job_id or checks['kind'] != 'extraction_check'
                    or checks['parent_result_id'] != extraction_id
                    or not isinstance(extraction['context_json'], dict)
                    or extraction['context_json'].get('attempt_token') != token
                    or checks['context_json'] != extraction['context_json']
                    or canonical_sha256(extraction['payload_json']) != extraction['content_sha256']
                    or canonical_sha256(checks['payload_json']) != checks['content_sha256']):
                raise ResultConflict('저장된 결과의 관계 또는 해시가 일치하지 않습니다')
            return {'extraction': extraction['payload_json'], 'checks': checks['payload_json'],
                    'extraction_result_id': extraction_id, 'check_result_id': check_id,
                    'extraction_sha256': extraction['content_sha256'],
                    'checks_sha256': checks['content_sha256'], 'attempt_token': token,
                    'extracted_at': extraction['context_json'].get('extracted_at'),
                    'extracted_at_source': extraction['context_json'].get('extracted_at_source')}
