"""모델 호출의 공통 동시성 제한과 대기 우선순위.

동기 호출과 비동기 호출은 같은 대기열을 사용한다. 기본 게이트는 같은 호스트의
프로세스들이 로컬 파일 시스템에서 공유한다. 네트워크 파일 시스템이나 여러
호스트에 걸친 조정에는 사용하지 않는다.
"""
from __future__ import annotations

import asyncio
import fcntl
import os
import sqlite3
import threading
import uuid
from collections import deque
from contextlib import asynccontextmanager, closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Iterator, Literal

Kind = Literal["extract", "reextract", "explain"]
_KINDS = frozenset(("extract", "reextract", "explain"))

# fork된 자식이 부모의 실행 중 잠금을 계속 보유하지 않도록 자식에서 FD를 닫는다.
_lease_fds: set[int] = set()
_lease_fds_lock = threading.Lock()


def _after_fork_child() -> None:
    global _default_lock
    for fd in _lease_fds:
        try:
            os.close(fd)
        except OSError:
            pass
    _lease_fds.clear()
    _lease_fds_lock.release()
    _default_lock = threading.Lock()


os.register_at_fork(before=_lease_fds_lock.acquire, after_in_parent=_lease_fds_lock.release,
                    after_in_child=_after_fork_child)


@dataclass(eq=False)
class _Waiter:
    kind: Kind
    event: threading.Event = field(default_factory=threading.Event)
    loop: asyncio.AbstractEventLoop | None = None
    future: asyncio.Future[None] | None = None
    granted: bool = False


class ModelGate:
    """공유 상한, 추출 우선 순위와 FIFO를 지키는 프로세스 내 게이트."""

    def __init__(self, max_inflight: int):
        if isinstance(max_inflight, bool) or not isinstance(max_inflight, int) or max_inflight < 1:
            raise ValueError("max_inflight는 1 이상의 정수여야 합니다")
        self.max_inflight = max_inflight
        self._lock = threading.Lock()
        self._active = 0
        self._high: deque[_Waiter] = deque()
        self._low: deque[_Waiter] = deque()

    def _enqueue(self, waiter: _Waiter) -> None:
        if waiter.kind not in _KINDS:
            raise ValueError(f"알 수 없는 모델 호출 종류: {waiter.kind}")
        with self._lock:
            (self._low if waiter.kind == "explain" else self._high).append(waiter)
            self._dispatch_locked()

    @staticmethod
    def _notify_future(future: asyncio.Future[None]) -> None:
        if not future.done():
            future.set_result(None)

    def _dispatch_locked(self) -> None:
        while self._active < self.max_inflight and (self._high or self._low):
            waiter = (self._high if self._high else self._low).popleft()
            waiter.granted = True
            self._active += 1
            if waiter.loop is None:
                waiter.event.set()
            else:
                assert waiter.future is not None
                try:
                    waiter.loop.call_soon_threadsafe(self._notify_future, waiter.future)
                except RuntimeError:  # 이벤트 루프가 이미 닫힌 요청은 슬롯을 점유하지 않는다.
                    waiter.granted = False
                    self._active -= 1

    def _cancel_or_release(self, waiter: _Waiter) -> None:
        with self._lock:
            if waiter.granted:
                waiter.granted = False
                self._active -= 1
            else:
                queue = self._low if waiter.kind == "explain" else self._high
                try:
                    queue.remove(waiter)
                except ValueError:
                    pass
            self._dispatch_locked()

    @contextmanager
    def slot_sync(self, kind: Kind) -> Iterator[None]:
        """스레드에서 슬롯을 얻고, 예외가 나도 반환한다."""
        waiter = _Waiter(kind)
        self._enqueue(waiter)
        try:
            waiter.event.wait()
            yield
        finally:
            self._cancel_or_release(waiter)

    @asynccontextmanager
    async def slot(self, kind: Kind) -> AsyncIterator[None]:
        """이벤트 루프를 막지 않고 슬롯을 얻는다. 대기 중 취소도 처리한다."""
        loop = asyncio.get_running_loop()
        waiter = _Waiter(kind, loop=loop, future=loop.create_future())
        self._enqueue(waiter)
        try:
            await waiter.future
            yield
        finally:
            self._cancel_or_release(waiter)


class _Lease:
    def __init__(self, token: str, fd: int):
        self.token = token
        self.fd = fd
        self.pid = os.getpid()


class ProcessModelGate:
    """로컬 SQLite와 OS 잠금으로 같은 호스트의 프로세스가 상한을 공유한다.

    프로세스가 비정상 종료하면 요청별 파일 잠금이 OS에 의해 반환된다. 다른
    호출자가 대기열을 검사할 때 그 요청과 점유 슬롯을 회수한다. 상태 디렉터리는
    반드시 모든 프로세스가 같은 로컬 파일 시스템의 같은 경로로 지정해야 한다.
    """

    def __init__(self, max_inflight: int, state_dir: str | Path):
        if isinstance(max_inflight, bool) or not isinstance(max_inflight, int) or max_inflight < 1:
            raise ValueError("max_inflight는 1 이상의 정수여야 합니다")
        self.max_inflight = max_inflight
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.state_dir.is_symlink() or self.state_dir.stat().st_uid != os.getuid():
            raise ValueError("모델 게이트 디렉터리는 현재 사용자가 소유한 실제 디렉터리여야 합니다")
        if self.state_dir.stat().st_mode & 0o077:
            raise ValueError("모델 게이트 디렉터리는 다른 사용자가 접근할 수 없어야 합니다")
        self._database = self.state_dir / "queue.sqlite3"
        with closing(self._connect()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK (id = 1), capacity INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS requests (seq INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, granted INTEGER NOT NULL DEFAULT 0)")

    def _connect(self, *, nonblocking: bool = False) -> sqlite3.Connection:
        return sqlite3.connect(self._database, timeout=0 if nonblocking else 5, isolation_level=None)

    def _lease_path(self, token: str) -> Path:
        return self.state_dir / (token + ".lock")

    def _is_live(self, token: str) -> bool:
        try:
            fd = os.open(self._lease_path(token), os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return False
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        finally:
            os.close(fd)

    def _remove_stale(self, db: sqlite3.Connection) -> None:
        for (token,) in db.execute("SELECT token FROM requests").fetchall():
            if not self._is_live(token):
                db.execute("DELETE FROM requests WHERE token = ?", (token,))
                self._lease_path(token).unlink(missing_ok=True)

    def _transaction(self, fn, *, nonblocking: bool = False):
        with closing(self._connect(nonblocking=nonblocking)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._remove_stale(db)
                result = fn(db)
                db.execute("COMMIT")
                return result
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def _register(self, kind: Kind, *, nonblocking: bool = False) -> _Lease:
        if kind not in _KINDS:
            raise ValueError(f"알 수 없는 모델 호출 종류: {kind}")
        token = uuid.uuid4().hex
        with _lease_fds_lock:
            fd = os.open(self._lease_path(token), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            _lease_fds.add(fd)
        lease = _Lease(token, fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)

            def register(db):
                row = db.execute("SELECT capacity FROM settings WHERE id=1").fetchone()
                count = db.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
                if row and row[0] != self.max_inflight and count:
                    raise ValueError("다른 프로세스의 MSDS_MODEL_MAX_INFLIGHT 설정과 다릅니다")
                db.execute("INSERT INTO settings(id, capacity) VALUES(1, ?) ON CONFLICT(id) DO UPDATE SET capacity=excluded.capacity", (self.max_inflight,))
                db.execute("INSERT INTO requests(token, kind) VALUES (?, ?)", (token, kind))

            self._transaction(register, nonblocking=nonblocking)
            return lease
        except BaseException:
            with _lease_fds_lock:
                os.close(fd)
                _lease_fds.discard(fd)
            self._lease_path(token).unlink(missing_ok=True)
            raise

    def _poll(self, lease: _Lease, *, nonblocking: bool = False) -> bool:
        def poll(db):
            granted = db.execute("SELECT COUNT(*) FROM requests WHERE granted=1").fetchone()[0]
            capacity = db.execute("SELECT capacity FROM settings WHERE id=1").fetchone()[0]
            free = capacity - granted
            if free > 0:
                rows = db.execute("SELECT token FROM requests WHERE granted=0 ORDER BY CASE WHEN kind='explain' THEN 1 ELSE 0 END, seq LIMIT ?", (free,)).fetchall()
                db.executemany("UPDATE requests SET granted=1 WHERE token=?", rows)
            row = db.execute("SELECT granted FROM requests WHERE token=?", (lease.token,)).fetchone()
            if row is None:
                raise RuntimeError("모델 게이트 요청이 사라졌습니다")
            return bool(row[0])
        return self._transaction(poll, nonblocking=nonblocking)

    def _release(self, lease: _Lease, *, nonblocking: bool = False) -> None:
        if lease.pid != os.getpid():
            return  # fork된 자식은 부모 요청을 삭제하거나 슬롯을 반환하지 않는다.
        try:
            self._transaction(lambda db: db.execute("DELETE FROM requests WHERE token=?", (lease.token,)), nonblocking=nonblocking)
        finally:
            with _lease_fds_lock:
                os.close(lease.fd)
                _lease_fds.discard(lease.fd)
            self._lease_path(lease.token).unlink(missing_ok=True)

    def _acquire(self, kind: Kind, cancelled: threading.Event) -> _Lease | None:
        lease = self._register(kind)
        try:
            while not cancelled.is_set():
                if self._poll(lease):
                    if not cancelled.is_set():
                        return lease
                    break
                cancelled.wait(0.03)
        except BaseException:
            self._release(lease)
            raise
        self._release(lease)
        return None

    @contextmanager
    def slot_sync(self, kind: Kind) -> Iterator[None]:
        lease = self._acquire(kind, threading.Event())
        assert lease is not None
        try:
            yield
        finally:
            self._release(lease)

    @asynccontextmanager
    async def slot(self, kind: Kind) -> AsyncIterator[None]:
        # SQLite 잠금이 잡혀 있으면 이벤트 루프를 블록하지 않고 재시도한다.
        def locked(exc: sqlite3.OperationalError) -> bool:
            return getattr(exc, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)

        while True:
            try:
                lease = self._register(kind, nonblocking=True)
                break
            except sqlite3.OperationalError as exc:
                if not locked(exc):
                    raise
                await asyncio.sleep(0.03)
        try:
            while True:
                try:
                    if self._poll(lease, nonblocking=True):
                        break
                except sqlite3.OperationalError as exc:
                    if not locked(exc):
                        raise
                await asyncio.sleep(0.03)
            yield
        finally:
            try:
                self._release(lease, nonblocking=True)
            except sqlite3.OperationalError as exc:
                # 잠금을 얻지 못해도 파일 잠금은 반환된다. 다음 호출이 오래된 행을 회수한다.
                if not locked(exc):
                    raise


_default_gate: ProcessModelGate | None = None
_default_lock = threading.Lock()


def get_model_gate() -> ProcessModelGate:
    """환경 설정을 처음 사용할 때 읽고 호출자들이 하나의 게이트를 공유한다."""
    global _default_gate
    with _default_lock:
        if _default_gate is None:
            raw = os.environ.get("MSDS_MODEL_MAX_INFLIGHT", "16")
            try:
                limit = int(raw)
            except ValueError as exc:
                raise ValueError("MSDS_MODEL_MAX_INFLIGHT는 1 이상의 정수여야 합니다") from exc
            state_dir = os.environ.get("MSDS_MODEL_GATE_DIR", f"/tmp/to21-msds-model-gate-{os.getuid()}")
            _default_gate = ProcessModelGate(limit, state_dir)
        return _default_gate
