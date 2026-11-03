"""문서를 한 번에 한 건씩 처리하는 작업자 스레드 (서비스 API).

한 건 안에서 이미 항별로 16개를 동시에 부르므로 문서끼리는 차례로 돌린다. 화면도 '한 번에 한 건씩 올립니다'다.
"""
from __future__ import annotations

import queue
import logging
import json
import copy
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

import yaml

from msds.service.store import DocumentStore

LOG = logging.getLogger(__name__)


class Worker:
    def __init__(self, store: DocumentStore, process: Callable[[DocumentStore, str], None]):
        self.store = store
        self.process = process
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="msds-extract-worker", daemon=True)
            self._thread.start()

    def submit(self, doc_id: str) -> None:
        self._queue.put(doc_id)

    def stop(self, timeout: float | None = None) -> None:
        """대기열을 닫는다. 돌고 있는 문서는 끝까지 기다리지 않는다(timeout). 다음에 켤 때 store.recover가 정리한다."""
        if self._thread is not None:
            self._queue.put(None)
            self._thread.join(timeout)
            self._thread = None

    def _loop(self) -> None:
        while (doc_id := self._queue.get()) is not None:
            self.process(self.store, doc_id)


class PostgresWorker:
    """Independent preprocessing and extraction workers backed by DB leases.

    ``submit`` is intentionally a no-op: insertion into PostgreSQL is the
    notification, so restarting an API process cannot lose queued work.
    """

    def __init__(self, store, *, steps=None, pages_dir: Path | None = None,
                 work_dir: Path | None = None, preprocess_workers: int = 1,
                 extract_workers: int = 1, poll_seconds: float = 1.0,
                 lease_seconds: float = 120.0, result_store=None):
        if preprocess_workers < 1 or extract_workers < 1:
            raise ValueError('Both worker counts must be positive')
        if poll_seconds <= 0 or lease_seconds <= 0:
            raise ValueError('Poll and lease intervals must be positive')
        from msds.common import paths
        from msds.service import pipeline

        self.store = store
        self.result_store = result_store
        self.steps = steps or pipeline.Steps()
        self.pages_dir = Path(pages_dir or paths.PAGES)
        self.work_dir = Path(work_dir or store.root)
        self.preprocess_workers = preprocess_workers
        self.extract_workers = extract_workers
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self._threads = [thread for thread in self._threads if thread.is_alive()]
            if self._threads:
                return
            if hasattr(self.store, "validate_schema"):
                self.store.validate_schema()
            if self.result_store is not None:
                self.result_store.validate_schema()
            self._stop.clear()
            for stage, count in (('preprocess', self.preprocess_workers), ('extract', self.extract_workers)):
                for index in range(count):
                    thread = threading.Thread(target=self._loop, args=(stage,),
                                              name=f'msds-{stage}-{index}', daemon=True)
                    self._threads.append(thread)
                    thread.start()

    def submit(self, doc_id: str) -> None:
        """The job is already queued in PostgreSQL; there is no volatile queue."""

    def stop(self, timeout: float | None = None) -> None:
        self._stop.set()
        deadline = None if timeout is None else time.monotonic() + max(0, timeout)
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            remaining = None if deadline is None else max(0, deadline - time.monotonic())
            thread.join(remaining)
        # Threads executing work may outlive the timeout. They keep their lease
        # alive and finish normally; do not launch duplicates on a later start.

    def _loop(self, stage: str) -> None:
        while not self._stop.is_set():
            try:
                self.store.recover_expired()
                job = self.store.claim(stage=stage, lease_seconds=self.lease_seconds)
                if job is not None:
                    self._execute(stage, job)
                    continue
            except Exception:
                LOG.exception('Could not poll %s jobs', stage)
            self._stop.wait(self.poll_seconds)

    def _execute(self, stage: str, job: dict) -> None:
        from msds.service.jobs import LeaseLost

        doc_id, token = job['id'], job['lease_token']
        bound = self.store.bind(doc_id, token)
        heartbeat_stop = threading.Event()

        def heartbeat() -> None:
            while not heartbeat_stop.wait(max(0.05, self.lease_seconds / 3)):
                try:
                    if not self.store.heartbeat(doc_id, token, self.lease_seconds):
                        return
                except Exception:
                    LOG.exception('Could not renew job lease')

        pulse = threading.Thread(target=heartbeat, name=f'msds-heartbeat-{doc_id}', daemon=True)
        pulse.start()
        try:
            attempt = self.store.attempt_paths(doc_id, token)
            if stage == 'preprocess':
                self._preprocess(bound, doc_id, attempt)
                self.store.queue_next(doc_id, token)
            else:
                prepared = self.store.attempt_paths(doc_id, job['_prepared_token'])
                for key in ('pages_dir', 'sections_dir'):
                    shutil.copytree(prepared[key], attempt[key], dirs_exist_ok=False)
                self._extract(bound, doc_id, attempt, token)
                self.store.complete(doc_id, token)
                if self.result_store is not None and os.environ.get('MSDS_AUTO_HANDOFF') == '1':
                    try:
                        from msds.service.handoff import extraction_date, publish_handoff
                        saved = self.result_store.get_active(doc_id)
                        as_of = extraction_date(saved['extracted_at'])
                        publish_handoff(self.store, doc_id, as_of=as_of, schema=self.store.schema)
                    except Exception as exc:
                        LOG.exception('Could not publish automatic handoff for %s', doc_id)
                        self.store.fail_handoff(doc_id, token,
                            f'자동 판정 전달 실패: {type(exc).__name__}: {str(exc)[:400]}')
        except LeaseLost:
            LOG.warning('Job lease lost for %s; discarding this worker result', doc_id)
        except Exception as exc:
            LOG.exception('Job %s failed during %s', doc_id, stage)
            try:
                self.store.complete(doc_id, token, error=f'{type(exc).__name__}: {str(exc)[:450]}')
            except LeaseLost:
                LOG.warning('Job %s failed after its lease was lost', doc_id)
            except Exception:
                # An indeterminate commit must not cause a second immediate run.
                # The normal expired-lease recovery will revisit it later.
                LOG.exception('Could not record failure for job %s', doc_id)
        finally:
            heartbeat_stop.set()
            pulse.join()

    def _preprocess(self, store, doc_id: str, attempt: dict[str, Path]) -> None:
        def emit(event):
            store.apply(doc_id, event)

        attempt['pages_dir'].mkdir(parents=True, exist_ok=True)
        attempt['sections_dir'].mkdir(parents=True, exist_ok=True)
        meta = self.steps.preprocess(store.pdf_path(doc_id), doc_id, force=True,
                                     on_page=lambda page, total: emit({'type': 'page', 'page': page, 'total': total}),
                                     pages_root=attempt['pages_dir'])
        emit({'type': 'preprocess_done', 'page_count': meta['page_count'], 'text_layer': meta.get('text_layer')})
        emit({'type': 'stage', 'stage': 'sections'})
        self.steps.sections(doc_id, attempt['pages_dir'], attempt['sections_dir'])

    def _extract(self, store, doc_id: str, attempt: dict[str, Path], token: str) -> None:
        def emit(event):
            store.apply(doc_id, event)

        state = store.get(doc_id)
        if state is None:
            raise KeyError(doc_id)
        tag = state['model_tag']
        emit({'type': 'stage', 'stage': 'extract'})
        runs_dir = attempt['runs_dir']
        self.steps.save_run_info(runs_dir / doc_id, tag, attempt['pages_dir'])
        reused = self._reuse_completed(store, state, attempt, emit) if self.result_store is not None else None
        if reused is not None:
            summary, source_job = reused
            emit({'type': 'reused', 'job_id': source_job})
        else:
            summary = self.steps.extract(doc_id, tag, doc_id, pages_dir=attempt['pages_dir'],
                                         sections_dir=attempt['sections_dir'], runs_dir=runs_dir, on_event=emit)
        if self.result_store is not None:
            from msds.checks.final_validation import summarize_checks
            from msds.common.merge import now_kst

            run = runs_dir / doc_id
            extraction = json.loads((run / 'outputs' / f'{doc_id}.json').read_text(encoding='utf-8'))
            checks = json.loads((run / 'checks' / f'{doc_id}.json').read_text(encoding='utf-8'))
            validation = summarize_checks(extraction, checks)
            extracted_at = (extraction.get('doc', {}).get('extraction') or {}).get('extracted_at') or now_kst()
            self.result_store.save_for_lease(doc_id, token, extraction, checks, extracted_at=extracted_at)
            summary = {**summary, 'validation': validation, 'results_persisted': True}
        emit({'type': 'done', 'summary': summary})

    def _reuse_completed(self, store, state: dict, attempt: dict[str, Path], emit) -> tuple[dict, str] | None:
        """Reuse only an identical, completed extraction; reviews stay job-local."""
        if not state.get('reuse_requested', True) or not state.get('duplicate_of'):
            return None
        from msds.checks.final_validation import summarize_checks
        from msds.extract.section_runner import raw_path
        from msds.service.results import ResultConflict, ResultNotReady

        job_id = state['id']
        run = attempt['runs_dir'] / job_id
        try:
            current_info = yaml.safe_load((run / 'run_info.yaml').read_text(encoding='utf-8')) or {}
        except (OSError, yaml.YAMLError):
            return None
        keys = ('model_tag', 'model_config_sha256', 'prompt_hashes', 'schema_version',
                'dictionary_version', 'git_commit', 'rows_sections', 'rows_max_tokens', 'image_input')
        if not current_info.get('git_commit') or not current_info.get('dictionary_version'):
            return None
        for previous_id in reversed(state.get('duplicate_of') or []):
            previous = store.get(previous_id)
            if (not previous or previous['status'] != 'done' or previous['model_tag'] != state['model_tag']
                    or previous.get('as_of') != state.get('as_of')):
                continue
            published = store.artifact_paths(previous_id)
            if published is None:
                continue
            old_run = published['runs_dir'] / previous_id
            try:
                old_info = yaml.safe_load((old_run / 'run_info.yaml').read_text(encoding='utf-8')) or {}
                if any(old_info.get(key) != current_info.get(key) for key in keys):
                    continue
                saved = self.result_store.get_active(previous_id)
                extraction, checks = copy.deepcopy(saved['extraction']), copy.deepcopy(saved['checks'])
                # `done` means the attempt ended, not that every section or
                # validator succeeded. Never cache a failure or missing checks.
                if summarize_checks(extraction, checks)['status'] == 'invalid':
                    continue
                plan = [{key: item[key] for key in ('msds_index', 'section', 'title', 'pages')}
                        for item in previous['sections']]
                if len(plan) != len(checks['sections']):
                    continue
                raw_rows = []
                for section in checks['sections']:
                    source_path = raw_path(old_run, previous_id, section['msds_index'], section['section'])
                    raw_rows.append((section, json.loads(source_path.read_text(encoding='utf-8'))))
                extraction['doc']['doc_id'] = job_id
                extraction['doc']['source_file'] = state['filename']
            except (KeyError, ValueError, OSError, TypeError, yaml.YAMLError,
                    ResultConflict, ResultNotReady):
                continue
            for section, raw in raw_rows:
                target = raw_path(run, job_id, section['msds_index'], section['section'])
                target.parent.mkdir(parents=True, exist_ok=True)
                raw['doc_id'] = job_id
                target.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding='utf-8')
            for directory, payload in (('outputs', extraction), ('checks', checks)):
                target = run / directory / f'{job_id}.json'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
            emit({'type': 'plan', 'msds_count': len(extraction['msds']),
                  'page_count': previous.get('page_count'),
                  'sections': plan})
            review = {(item['msds_index'], item['section']) for item in checks.get('needs_review', [])}
            for section in checks['sections']:
                emit({'type': 'section_done', 'msds_index': section['msds_index'],
                      'section': section['section'], 'ok': section['ok'],
                      'reextracted': section.get('reextracted', False),
                      'needs_review': (section['msds_index'], section['section']) in review,
                      'seconds': 0, 'errors': section.get('errors', [])})
            emit({'type': 'finalize'})
            summary = {'doc_id': job_id, 'seconds': 0, 'sections_ok': sum(s['ok'] for s in checks['sections']),
                       'sections_failed': sum(not s['ok'] for s in checks['sections']),
                       'reextracted': sum(s.get('reextracted', False) for s in checks['sections']),
                       'schema_errors': len(checks.get('schema_errors', [])),
                       'warnings': list(checks.get('warnings', []))}
            return summary, previous_id
        return None
