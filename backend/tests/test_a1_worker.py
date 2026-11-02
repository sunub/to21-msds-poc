"""Stage orchestration against an in-memory queue and fake processing steps."""
from __future__ import annotations

import threading
import time
import uuid
from types import SimpleNamespace

import pytest

from msds.service import progress
from msds.service.jobs import LeaseLost
from msds.service.worker import PostgresWorker


def test_worker_does_not_start_with_invalid_schema(tmp_path):
    class InvalidStore:
        root = tmp_path

        def validate_schema(self):
            raise RuntimeError("마이그레이션을 확인하세요")

    worker = PostgresWorker(InvalidStore())
    with pytest.raises(RuntimeError, match="마이그레이션"):
        worker.start()
    assert worker._threads == []


class Queue:
    def __init__(self, root, count=1):
        self.root = root
        self.lock = threading.RLock()
        self.states = {}
        self.tokens = {}
        self.attempts = {}
        for i in range(count):
            ident = f'U-20261103-{i + 1:03}'
            self.states[ident] = progress.new_state(ident, 'a.pdf', 'a' * 64, 10, None, 'model', '2026-11-03T00:00:00+09:00')

    def recover_expired(self):
        return 0

    def claim(self, stage='preprocess', lease_seconds=120):
        with self.lock:
            for ident, state in self.states.items():
                phase = 'extract' if state['stage'] == 'extract' else 'preprocess'
                if state['status'] != 'queued' or phase != stage:
                    continue
                token = self.tokens[ident] = uuid.uuid4().hex
                if stage == 'preprocess':
                    self.attempts[ident] = self.attempts.get(ident, 0) + 1
                    progress.apply_event(state, {'type': 'started'})
                else:
                    state['status'] = 'running'
                state['_working_token'] = token
                return {**state, 'lease_token': token}

    def heartbeat(self, ident, token, lease_seconds=120):
        with self.lock:
            return self.tokens.get(ident) == token

    def bind(self, ident, token):
        parent = self

        class Bound:
            def pdf_path(self, doc_id):
                return parent.root / doc_id / 'source.pdf'

            def get(self, doc_id):
                with parent.lock:
                    return dict(parent.states[doc_id])

            def apply(self, doc_id, event):
                with parent.lock:
                    if parent.tokens.get(doc_id) != token or doc_id != ident:
                        raise LeaseLost(doc_id)
                    return progress.apply_event(parent.states[doc_id], event)

        return Bound()

    def attempt_paths(self, ident, token):
        base = self.root / '.attempts' / ident / token
        return {'pages_dir': base / 'pages', 'sections_dir': base / 'sections', 'runs_dir': base / 'runs'}

    def queue_next(self, ident, token):
        with self.lock:
            if self.tokens.get(ident) != token:
                raise LeaseLost(ident)
            self.states[ident].update(status='queued', stage='extract')
            self.states[ident]['_prepared_token'] = token
            del self.tokens[ident]

    def complete(self, ident, token, *, error=None):
        with self.lock:
            if self.tokens.get(ident) != token:
                raise LeaseLost(ident)
            if error is not None:
                progress.apply_event(self.states[ident], {'type': 'failed', 'error': error})
                if self.attempts[ident] < 2:
                    progress.apply_event(self.states[ident], {'type': 'queued'})
            del self.tokens[ident]
            return self.states[ident]


def wait_for(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Timed out waiting for a worker')


def test_preprocessing_continues_while_model_worker_is_busy(tmp_path):
    store = Queue(tmp_path, count=2)
    started, release = threading.Event(), threading.Event()
    preprocessed = []

    def preprocess(path, doc_id, *, force, on_page, pages_root):
        preprocessed.append(doc_id)
        (pages_root / doc_id).mkdir(parents=True)
        (pages_root / doc_id / 'p001.txt').write_text(doc_id)
        on_page(1, 1)
        return {'page_count': 1, 'text_layer': '정상'}

    def extract(doc_id, *args, **kwargs):
        assert (kwargs['pages_dir'] / doc_id / 'p001.txt').read_text() == doc_id
        started.set()
        assert release.wait(3)
        return {'sections_ok': 1}

    steps = SimpleNamespace(preprocess=preprocess, sections=lambda *a: None,
                            save_run_info=lambda *a: None, extract=extract)
    worker = PostgresWorker(store, steps=steps, poll_seconds=0.01, lease_seconds=1)
    try:
        worker.start()
        assert started.wait(3)
        wait_for(lambda: len(preprocessed) == 2)
        release.set()
        wait_for(lambda: all(state['status'] == 'done' for state in store.states.values()))
    finally:
        release.set()
        worker.stop(timeout=3)
    assert all(state['summary']['sections_ok'] == 1 for state in store.states.values())


def test_failed_preprocessing_retries_once_then_worker_continues(tmp_path):
    store = Queue(tmp_path)
    calls = []

    def preprocess(path, doc_id, *, force, on_page, pages_root):
        calls.append(doc_id)
        if len(calls) == 1:
            raise RuntimeError('transient failure')
        return {'page_count': 1, 'text_layer': '정상'}

    steps = SimpleNamespace(preprocess=preprocess, sections=lambda *a: None,
                            save_run_info=lambda *a: None, extract=lambda *a, **kw: {})
    worker = PostgresWorker(store, steps=steps, poll_seconds=0.01, lease_seconds=1)
    try:
        worker.start()
        wait_for(lambda: next(iter(store.states.values()))['status'] == 'done')
    finally:
        worker.stop(timeout=3)
    assert len(calls) == 2

