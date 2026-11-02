"""백그라운드 작업자: 판정 한 줄, 설명 여러 줄. 추출(A)의 대기열과 섞이지 않는다."""
import os
import threading
import time


class Workers:
    def __init__(self, service, explain_workers: int | None = None, idle_seconds: float = 1.0):
        self.service, self.idle = service, idle_seconds
        self.n_explain = explain_workers or int(os.environ.get("MSDS_EXPLAIN_WORKERS", "2"))
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def _loop(self, step) -> None:
        while not self._stop.is_set():
            try:
                busy = step()
            except Exception as e:  # DB가 잠깐 끊겨도 작업자는 죽지 않고 다시 시도한다
                print(f"판정 작업자 오류: {type(e).__name__}: {e}")
                busy = False
            if not busy:
                self._stop.wait(self.idle)

    def start(self) -> None:
        self.service.recover_if_alone()
        steps = [self.service.judge_step] + [self.service.explain_step] * self.n_explain
        self._threads = [threading.Thread(target=self._loop, args=(s,), daemon=True, name=f"judge-{i}") for i, s in enumerate(steps)]
        for t in self._threads:
            t.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        deadline = time.monotonic() + timeout
        for t in self._threads:
            t.join(max(deadline - time.monotonic(), 0))
