"""문서를 한 번에 한 건씩 처리하는 작업자 스레드 (서비스 API).

한 건 안에서 이미 항별로 16개를 동시에 부르므로 문서끼리는 차례로 돌린다. 화면도 '한 번에 한 건씩 올립니다'다.
"""
from __future__ import annotations

import queue
import threading
from typing import Callable

from msds.service.store import DocumentStore


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
