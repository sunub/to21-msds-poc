"""PostgreSQL-backed extraction job state with fenced worker leases.

The migration owns the table definition; this module never creates or alters DB
objects on startup. PDFs and review files remain in DocumentStore's directory.
Each worker must use ``bind(job_id, token)`` for *all* pipeline event writes.
"""
from __future__ import annotations

import math
import copy
import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from msds.common.merge import now_kst
from msds.service import progress, review


class LeaseLost(RuntimeError):
    """A worker no longer owns this job, so it must stop publishing progress."""


class ReviewNotReady(RuntimeError):
    """A review update raced with retry or the job has no completed result."""


def _unpublish_active(state: dict) -> None:
    token = state.pop('_active_token', None)
    if token:
        history = state.setdefault('_previous_artifacts', [])
        if not history or history[-1] != token:
            history.append(token)


def _record_attempt_end(attempts: list[dict], attempt_no: int, state: dict) -> None:
    current = next((a for a in reversed(attempts)
                    if a.get('attempt') == attempt_no and a.get('status') == 'running'), None)
    if current is None:
        current = {'attempt': attempt_no}
        attempts.append(current)
    current.update(status=state['status'], error=state.get('error'), finished_at=now_kst())


def _duration_estimate(attempts_by_job: list[list[dict]]) -> float | None:
    """75th percentile of successful wall-clock durations, one sample per job."""
    durations = []
    for attempts in attempts_by_job:
        for attempt in reversed(attempts):
            if attempt.get('status') != 'done':
                continue
            try:
                start = datetime.fromisoformat(attempt['started_at'])
                end = datetime.fromisoformat(attempt['finished_at'])
                seconds = (end - start).total_seconds()
            except (KeyError, ValueError, TypeError):
                continue
            if math.isfinite(seconds) and seconds > 0:
                durations.append(seconds)
                break
    if len(durations) < 3:
        return None
    durations.sort()
    return durations[math.ceil(len(durations) * .75) - 1]


class PostgresJobStore:
    def __init__(self, dsn: str, root: Path, taken_dirs: tuple[Path, ...] = (), *, schema: str = "extract"):
        if not dsn or not dsn.strip():
            raise ValueError("A PostgreSQL DSN is required")
        if not schema or '\x00' in schema or len(schema.encode('utf-8')) > 63:
            raise ValueError("Invalid PostgreSQL schema name")
        self.dsn = dsn
        self.schema = schema
        self.root = Path(root)
        self.taken_dirs = tuple(Path(p) for p in taken_dirs)
        self.table = sql.Identifier(schema, "jobs")
        self.root.mkdir(parents=True, exist_ok=True)

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5)

    def validate_schema(self) -> None:
        """Fail application startup if the selected DB lacks the A1 schema."""
        try:
            with self._connect() as db:
                db.execute(sql.SQL("""SELECT job_id, filename, file_sha256, size_bytes,
                    as_of, status, stage, model_tag, progress_json, attempt_no,
                    attempts_json, lease_token, lease_expires_at, created_at, updated_at
                    FROM {} LIMIT 0""").format(self.table))
        except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn) as exc:
            raise RuntimeError("추출 작업 테이블이 없거나 정의가 다릅니다. A1 마이그레이션을 확인하세요") from exc

    def pdf_path(self, doc_id: str) -> Path:
        if not re.fullmatch(r'U-\d{8}-\d{3,}', doc_id):
            raise ValueError('Invalid job identifier')
        return self.root / doc_id / 'source.pdf'

    def _review_path(self, doc_id: str, state: dict) -> Path:
        token = state.get('_active_token')
        if not token:
            raise ReviewNotReady(doc_id)
        return self.attempt_paths(doc_id, token)['runs_dir'].parent / 'review.json'

    def _load_review_locked(self, db, doc_id: str, state: dict) -> tuple[dict, str | None]:
        """Read the current result's review; older file reviews remain importable."""
        token = state.get('_active_token')
        if not token:
            raise ReviewNotReady(doc_id)
        result_id = f'a2-{doc_id}-{token}-extraction'
        result = None
        table = sql.Identifier(self.schema, 'results')
        if db.execute('SELECT to_regclass(%s)', (table.as_string(db),)).fetchone()['to_regclass']:
            result = db.execute(sql.SQL('SELECT result_id FROM {} WHERE job_id=%s AND result_id=%s AND kind=%s')
                                .format(table), (doc_id, result_id, 'extraction')).fetchone()
        if result:
            latest = db.execute(sql.SQL('SELECT after_json FROM {} WHERE job_id=%s AND result_id=%s '
                                        'ORDER BY review_seq DESC LIMIT 1')
                                .format(sql.Identifier(self.schema, 'reviews')),
                                (doc_id, result_id)).fetchone()
            if latest:
                return latest['after_json']['record'], result_id
        path = self._review_path(doc_id, state)
        record = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else review.empty()
        return record, result_id if result else None

    def load_review(self, doc_id: str) -> dict:
        with self._connect() as db:
            row = db.execute(sql.SQL('SELECT status, progress_json FROM {} WHERE job_id=%s FOR SHARE')
                             .format(self.table), (doc_id,)).fetchone()
            if row is None:
                raise KeyError(doc_id)
            if row['status'] != 'done':
                raise ReviewNotReady(doc_id)
            record, _ = self._load_review_locked(db, doc_id, row['progress_json'])
            return record

    def update_review(self, doc_id: str, change: Callable[[dict], None]) -> dict:
        # Serialize the result version and file mutation with retry's row lock.
        with self._connect() as db:
            row = db.execute(sql.SQL('SELECT status, progress_json FROM {} WHERE job_id=%s FOR UPDATE')
                             .format(self.table), (doc_id,)).fetchone()
            if row is None:
                raise KeyError(doc_id)
            if row['status'] != 'done':
                raise ReviewNotReady(doc_id)
            record, result_id = self._load_review_locked(db, doc_id, row['progress_json'])
            before = copy.deepcopy(record)
            change(record)
            if result_id:
                if len(record['log']) != len(before['log']) + 1:
                    raise ValueError('검수 변경은 하나의 이벤트를 남겨야 합니다')
                event = record['log'][-1]
                action = event['action']
                if action not in ('confirm', 'edit', 'reset', 'section_confirm', 'section_unconfirm'):
                    raise ValueError('알 수 없는 검수 동작입니다')
                sequence = db.execute(sql.SQL('SELECT COALESCE(max(review_seq), 0) + 1 AS seq FROM {} '
                                              'WHERE job_id=%s')
                                      .format(sql.Identifier(self.schema, 'reviews')),
                                      (doc_id,)).fetchone()['seq']
                db.execute(sql.SQL('''INSERT INTO {} (review_id, job_id, result_id, review_seq,
                    msds_index, field_path, section_no, action, before_json, after_json, reviewer, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''')
                    .format(sql.Identifier(self.schema, 'reviews')),
                    (uuid.uuid4().hex, doc_id, result_id, sequence, event['msds_index'],
                     event.get('path'), event.get('section'), action, Jsonb({'record': before}),
                     Jsonb({'record': record}), event['reviewer'], event['at']))
                return record
            path = self._review_path(doc_id, row['progress_json'])
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
            try:
                tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding='utf-8')
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
            return record

    def create(self, pdf: bytes, filename: str, as_of: str | None, model_tag: str,
               today: str | None = None) -> dict:
        # Serialize ID allocation with every API process using this database.
        # Never create state.json: file-mode workers must not pick up DB jobs.
        now = now_kst()
        today = today or now[:10].replace('-', '')
        if not re.fullmatch(r'\d{8}', today):
            raise ValueError('today must have YYYYMMDD format')
        digest = hashlib.sha256(pdf).hexdigest()
        with self._connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("msds-extract-create",))
            existing = db.execute(sql.SQL('SELECT job_id FROM {} WHERE job_id LIKE %s').format(self.table),
                                  (f'U-{today}-%',)).fetchall()
            pattern = re.compile(rf'^U-{today}-(\d{{3,}})$')
            numbers = [int(match.group(1)) for row in existing if (match := pattern.fullmatch(row['job_id']))]
            for directory in (self.root, *self.taken_dirs):
                if directory.is_dir():
                    numbers.extend(int(match.group(1)) for path in directory.iterdir()
                                   if (match := pattern.fullmatch(path.name)))
            serial = max(numbers, default=0) + 1
            while True:
                doc_id = f'U-{today}-{serial:03d}'
                try:
                    (self.root / doc_id).mkdir()
                    break
                except FileExistsError:
                    serial += 1
            duplicate_rows = db.execute(sql.SQL('SELECT job_id FROM {} WHERE file_sha256=%s ORDER BY job_id')
                                        .format(self.table), (digest,)).fetchall()
            state = progress.new_state(doc_id, filename, digest, len(pdf), as_of, model_tag, now,
                                       [row['job_id'] for row in duplicate_rows])
            # On an uncertain insert/commit outcome, preserve the original PDF.
            # Future allocations skip the orphan's directory and never overwrite it.
            self.pdf_path(doc_id).write_bytes(pdf)
            db.execute(sql.SQL("""INSERT INTO {} (job_id, filename, file_sha256, size_bytes,
                as_of, status, stage, model_tag, progress_json, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,'queued',NULL,%s,%s,%s,%s)""").format(self.table),
                (state['id'], state['filename'], state['sha256'], state['size'], state['as_of'],
                 state['model_tag'], Jsonb(state), state['created_at'], state['updated_at']))
        return state

    def get(self, doc_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(sql.SQL("SELECT progress_json FROM {} WHERE job_id=%s").format(self.table),
                             (doc_id,)).fetchone()
        return row['progress_json'] if row else None

    def list(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(sql.SQL("SELECT progress_json FROM {} ORDER BY created_at DESC, job_id DESC")
                              .format(self.table)).fetchall()
        return [r['progress_json'] for r in rows]

    def requeue(self, doc_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(sql.SQL("SELECT * FROM {} WHERE job_id=%s FOR UPDATE").format(self.table),
                             (doc_id,)).fetchone()
            if not row:
                raise KeyError(doc_id)
            state = row['progress_json']
            if row['status'] not in ('done', 'failed', 'interrupted') or not progress.can_retry(state):
                return None
            progress.apply_event(state, {'type': 'queued'})
            _unpublish_active(state)
            state.pop('_prepared_token', None)
            state.pop('_working_token', None)
            state.pop('_pending_terminal', None)
            state['updated_at'] = now_kst()
            db.execute(sql.SQL("""UPDATE {} SET status='queued', stage=NULL, progress_json=%s,
                attempt_no=0, lease_token=NULL, lease_expires_at=NULL, updated_at=now() WHERE job_id=%s""")
                .format(self.table), (Jsonb(state), doc_id))
        return state

    def claim(self, stage: str = 'preprocess', lease_seconds: float = 120) -> dict | None:
        if stage not in ('preprocess', 'extract'):
            raise ValueError('stage must be preprocess or extract')
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError('lease_seconds must be positive')
        token = uuid.uuid4().hex
        with self._connect() as db:
            row = db.execute(sql.SQL("""SELECT * FROM {} WHERE status='queued'
                AND CASE WHEN %s='preprocess' THEN stage IS NULL OR stage='preprocess' ELSE stage='extract' END
                ORDER BY created_at, job_id LIMIT 1 FOR UPDATE SKIP LOCKED""").format(self.table),
                (stage,)).fetchone()
            if not row:
                return None
            state = row['progress_json']
            if stage == 'preprocess':
                progress.apply_event(state, {'type': 'started'})
                state.pop('_prepared_token', None)
                attempts = row['attempts_json']
                attempts.append({'attempt': row['attempt_no'] + 1, 'status': 'running', 'started_at': now_kst()})
            else:
                state.update(status='running', stage='extract', error=None)
                if not state.get('_prepared_token'):
                    raise RuntimeError('Extraction job has no prepared artifact')
                attempts = row['attempts_json']
            state['_working_token'] = token
            state['updated_at'] = now_kst()
            db.execute(sql.SQL("""UPDATE {} SET status='running', stage=%s, progress_json=%s,
                attempt_no=attempt_no+%s, attempts_json=%s, lease_token=%s,
                lease_expires_at=clock_timestamp()+(%s * interval '1 second'), updated_at=now()
                WHERE job_id=%s""").format(self.table),
                (stage, Jsonb(state), int(stage == 'preprocess'), Jsonb(attempts), token, lease_seconds, row['job_id']))
        return {**state, 'lease_token': token}

    def heartbeat(self, doc_id: str, token: str, lease_seconds: float = 120) -> bool:
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError('lease_seconds must be positive')
        with self._connect() as db:
            result = db.execute(sql.SQL("""UPDATE {} SET lease_expires_at=clock_timestamp()+(%s * interval '1 second')
                WHERE job_id=%s AND status='running' AND lease_token=%s AND lease_expires_at>clock_timestamp()""")
                .format(self.table), (lease_seconds, doc_id, token))
            return result.rowcount == 1

    def _owned(self, db, doc_id: str, token: str):
        row = db.execute(sql.SQL("""SELECT * FROM {} WHERE job_id=%s AND status='running'
            AND lease_token=%s AND lease_expires_at>clock_timestamp() FOR UPDATE""").format(self.table),
            (doc_id, token)).fetchone()
        if row is None:
            raise LeaseLost(f'Lease lost for {doc_id}')
        return row

    def apply(self, doc_id: str, event: dict, *, lease_token: str) -> dict:
        with self._connect() as db:
            row = self._owned(db, doc_id, lease_token)
            state = row['progress_json']
            if event.get('type') in ('done', 'failed'):
                # Do not expose completion before the worker commits it. API
                # clients must not read partially published artifacts.
                state['_pending_terminal'] = event
            else:
                progress.apply_event(state, event)
            state['updated_at'] = now_kst()
            # done/failed events are committed by finish; the lease stays valid
            # until then. This also allows the worker to perform auto retry.
            db.execute(sql.SQL("""UPDATE {} SET progress_json=%s, stage=%s, updated_at=now()
                WHERE job_id=%s AND lease_token=%s""").format(self.table),
                (Jsonb(state), state['stage'], doc_id, lease_token))
        return state

    def bind(self, doc_id: str, token: str):
        return _BoundJobStore(self, doc_id, token)

    def attempt_paths(self, doc_id: str, token: str) -> dict[str, Path]:
        """Resolve an isolated attempt path; never accept arbitrary DB paths."""
        if not re.fullmatch(r'U-\d{8}-\d{3,}', doc_id) or not re.fullmatch(r'[0-9a-f]{32}', token):
            raise ValueError('Invalid job or attempt identifier')
        base = self.root / '.attempts' / doc_id / token
        return {'pages_dir': base / 'pages', 'sections_dir': base / 'sections', 'runs_dir': base / 'runs'}

    def artifact_paths(self, doc_id: str) -> dict[str, Path] | None:
        """Return only paths published by a currently valid worker lease."""
        state = self.get(doc_id)
        if state is None:
            return None
        prepared = state.get('_prepared_token') or state.get('_active_token')
        if not prepared:
            return None
        paths = self.attempt_paths(doc_id, prepared)
        # During extraction, section results may be viewed as soon as their
        # fenced progress events arrive; their files are attempt-isolated.
        working = state.get('_working_token')
        run_token = working if state['status'] == 'running' and working and working != prepared else state.get('_active_token')
        if run_token:
            paths['runs_dir'] = self.attempt_paths(doc_id, run_token)['runs_dir']
        return paths

    def queue_next(self, doc_id: str, token: str, stage: str = 'extract') -> dict:
        if stage != 'extract':
            raise ValueError('Only the extraction stage can follow preprocessing')
        with self._connect() as db:
            row = self._owned(db, doc_id, token)
            state = row['progress_json']
            state.update(status='queued', stage='extract', updated_at=now_kst())
            state['_prepared_token'] = token
            db.execute(sql.SQL("""UPDATE {} SET status='queued', stage='extract', progress_json=%s,
                lease_token=NULL, lease_expires_at=NULL, updated_at=now() WHERE job_id=%s""")
                .format(self.table), (Jsonb(state), doc_id))
        return state

    def finish(self, doc_id: str, token: str, *, error: str | None = None) -> dict:
        with self._connect() as db:
            row = self._owned(db, doc_id, token)
            state = row['progress_json']
            pending = state.pop('_pending_terminal', None)
            if error is not None:
                progress.apply_event(state, {'type': 'failed', 'error': error[:500]})
            elif pending is not None:
                progress.apply_event(state, pending)
            elif state['status'] not in ('done', 'failed'):
                progress.apply_event(state, {'type': 'failed', 'error': '작업이 완료 이벤트 없이 종료됐습니다'})
            if state['status'] == 'done':
                state['_active_token'] = token
                state['_prepared_token'] = token
            attempts = row['attempts_json']
            _record_attempt_end(attempts, row['attempt_no'], state)
            if state['status'] == 'failed' and row['attempt_no'] < 2:
                progress.apply_event(state, {'type': 'queued'})
                _unpublish_active(state)
                state.pop('_prepared_token', None)
                state.pop('_working_token', None)
            state['updated_at'] = now_kst()
            db.execute(sql.SQL("""UPDATE {} SET status=%s, stage=%s, progress_json=%s,
                attempts_json=%s, lease_token=NULL, lease_expires_at=NULL, updated_at=now()
                WHERE job_id=%s""").format(self.table),
                (state['status'], state['stage'], Jsonb(state), Jsonb(attempts), doc_id))
        return state

    def complete(self, doc_id: str, token: str, *, error: str | None = None) -> dict:
        return self.finish(doc_id, token, error=error)

    def recover_expired(self) -> int:
        with self._connect() as db:
            rows = db.execute(sql.SQL("""SELECT * FROM {} WHERE status='running'
                AND lease_expires_at<=clock_timestamp() FOR UPDATE SKIP LOCKED""").format(self.table)).fetchall()
            for row in rows:
                state = row['progress_json']
                progress.apply_event(state, {'type': 'interrupted'})
                attempts = row['attempts_json']
                _record_attempt_end(attempts, row['attempt_no'], state)
                progress.apply_event(state, {'type': 'queued'})
                _unpublish_active(state)
                state.pop('_prepared_token', None)
                state.pop('_working_token', None)
                state.pop('_pending_terminal', None)
                state['updated_at'] = now_kst()
                db.execute(sql.SQL("""UPDATE {} SET status='queued', stage=NULL, progress_json=%s,
                    attempts_json=%s, lease_token=NULL, lease_expires_at=NULL, updated_at=now() WHERE job_id=%s""")
                    .format(self.table), (Jsonb(state), Jsonb(attempts), row['job_id']))
        return len(rows)

    def recover(self) -> int:
        return self.recover_expired()

    def queue_info(self, doc_id: str, *, workers: int = 1) -> dict:
        if workers < 1:
            raise ValueError('Invalid queue estimate settings')
        with self._connect() as db:
            row = db.execute(sql.SQL("""SELECT status, stage, created_at, job_id FROM {} WHERE job_id=%s""")
                             .format(self.table), (doc_id,)).fetchone()
            if row is None:
                raise KeyError(doc_id)
            if row['status'] != 'queued':
                return {'queue_position': None, 'estimated_wait_seconds': None, 'estimated_completion_seconds': None}
            phase = 'extract' if row['stage'] == 'extract' else 'preprocess'
            count = db.execute(sql.SQL("""SELECT count(*) AS n FROM {} WHERE status='queued'
                AND CASE WHEN %s='extract' THEN stage='extract' ELSE stage IS NULL OR stage='preprocess' END
                AND (created_at, job_id) <= (%s, %s)""").format(self.table),
                (phase, row['created_at'], row['job_id'])).fetchone()['n']
            running = db.execute(sql.SQL("SELECT count(*) AS n FROM {} WHERE status='running'")
                                 .format(self.table)).fetchone()['n']
            samples = db.execute(sql.SQL("""SELECT attempts_json FROM {} WHERE status='done'
                ORDER BY updated_at DESC LIMIT 30""").format(self.table)).fetchall()
        duration = _duration_estimate([sample['attempts_json'] for sample in samples])
        # Active jobs count as a full wave: this intentionally does not assume
        # their unknown remaining time is zero. These estimates are indicative.
        wait = None if duration is None else math.ceil(math.floor((running + count - 1) / workers) * duration)
        completion = None if wait is None else math.ceil(wait + duration)
        return {'queue_position': count, 'estimated_wait_seconds': wait, 'estimated_completion_seconds': completion}


class _BoundJobStore:
    def __init__(self, store: PostgresJobStore, doc_id: str, token: str):
        self._store, self._doc_id, self._token = store, doc_id, token

    def __getattr__(self, name):
        return getattr(self._store, name)

    def apply(self, doc_id: str, event: dict) -> dict:
        if doc_id != self._doc_id:
            raise LeaseLost('A worker may only update its claimed job')
        return self._store.apply(doc_id, event, lease_token=self._token)
