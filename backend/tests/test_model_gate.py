"""실제 스레드/이벤트 루프를 사용해 공용 호출 창구 계약을 검증한다."""
import asyncio
import multiprocessing
import sqlite3
import threading
import time

import pytest

from msds.common import model_gate
from msds.common.model_gate import ModelGate, ProcessModelGate


def test_explanation_client_uses_explain_queue_without_changing_extract_default(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from msds.extract import client as extract_client

    kinds = []

    @contextmanager
    def slot(kind):
        kinds.append(kind)
        yield

    monkeypatch.setattr(extract_client, 'get_model_gate', lambda: SimpleNamespace(slot_sync=slot))
    client = extract_client.ChatClient.__new__(extract_client.ChatClient)
    client.cfg = {}
    client.model = 'test'
    client.token_param = 'max_tokens'
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: None)))
    client._request([], 'json_object', 'test', {}, 10)
    client.gate_kind = 'explain'
    client._request([], 'json_object', 'test', {}, 10)
    assert kinds == ['extract', 'explain']


def _process_call(path, kind, entered, release):
    gate = ProcessModelGate(1, path)
    with gate.slot_sync(kind):
        entered.put(kind)
        release.wait(timeout=5)


def _fork_child_while_holding(path, entered):
    ctx = multiprocessing.get_context("fork")
    gate = ProcessModelGate(1, path)
    with gate.slot_sync("extract"):
        child = ctx.Process(target=time.sleep, args=(2,))
        child.start()
        entered.put(child.pid)
        time.sleep(5)


def _wait_for_requests(path, expected):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with sqlite3.connect(path / "queue.sqlite3") as db:
            rows = db.execute("SELECT kind FROM requests").fetchall()
        if len(rows) == expected:
            return
        time.sleep(0.01)
    raise AssertionError(f"대기 요청 {expected}개가 나타나지 않음: {rows}")


def test_extract_and_reextract_precede_explain_and_keep_fifo():
    async def scenario():
        gate = ModelGate(1)
        entered = []

        async def call(kind, name):
            async with gate.slot(kind):
                entered.append(name)

        async with gate.slot("extract"):
            tasks = []
            for kind, name in [("explain", "low1"), ("extract", "high1"),
                               ("reextract", "high2"), ("explain", "low2")]:
                tasks.append(asyncio.create_task(call(kind, name)))
                await asyncio.sleep(0)  # 순서대로 대기열에 넣는다.
            assert entered == []
        await asyncio.gather(*tasks)
        assert entered == ["high1", "high2", "low1", "low2"]

    asyncio.run(scenario())


def test_async_cancellation_before_and_after_grant_releases_capacity():
    async def scenario():
        gate = ModelGate(1)

        async def wait_for_slot():
            async with gate.slot("extract"):
                pass

        # 첫 슬롯이 사용 중일 때 대기 작업을 취소한다.
        async with gate.slot("explain"):
            pending = asyncio.create_task(wait_for_slot())
            await asyncio.sleep(0)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending

        # 슬롯을 배정했지만 콜백이 실행되기 전 취소해도 반환된다.
        holder = gate.slot_sync("extract")
        holder.__enter__()
        pending = asyncio.create_task(wait_for_slot())
        await asyncio.sleep(0)
        holder.__exit__(None, None, None)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        async with asyncio.timeout(1):
            async with gate.slot("explain"):
                pass

    asyncio.run(scenario())


def test_sync_and_async_share_limit_and_exceptions_release():
    gate = ModelGate(1)
    sync_entered = threading.Event()
    sync_release = threading.Event()

    def synchronous():
        with gate.slot_sync("extract"):
            sync_entered.set()
            assert sync_release.wait(timeout=2)

    thread = threading.Thread(target=synchronous)
    thread.start()
    assert sync_entered.wait(timeout=2)

    async def scenario():
        entered = asyncio.Event()

        async def call():
            async with gate.slot("explain"):
                entered.set()
                raise RuntimeError("모델 실패")

        task = asyncio.create_task(call())
        await asyncio.sleep(0.02)
        assert not entered.is_set()
        sync_release.set()
        # 일부 샌드박스에서는 이벤트 루프의 socketpair 깨우기가 금지된다.
        # 타이머로 루프를 주기적으로 진행해 스레드의 완료를 관찰한다.
        async with asyncio.timeout(2):
            while not task.done():
                await asyncio.sleep(0.01)
        with pytest.raises(RuntimeError, match="모델 실패"):
            await asyncio.wait_for(task, timeout=2)
        async with asyncio.timeout(1):
            async with gate.slot("extract"):
                pass

    try:
        asyncio.run(scenario())
    finally:
        sync_release.set()
        thread.join(timeout=2)
    assert not thread.is_alive()


def test_thread_concurrency_never_exceeds_limit():
    gate = ModelGate(3)
    count = peak = 0
    lock = threading.Lock()
    start = threading.Barrier(12)

    def call():
        nonlocal count, peak
        start.wait(timeout=2)
        with gate.slot_sync("extract"):
            with lock:
                count += 1
                peak = max(peak, count)
            time.sleep(0.01)
            with lock:
                count -= 1

    threads = [threading.Thread(target=call) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert all(not thread.is_alive() for thread in threads)
    assert peak == 3


def test_configuration_validation_and_process_singleton(monkeypatch):
    for limit in (0, -1, True):
        with pytest.raises(ValueError):
            ModelGate(limit)
    gate = ModelGate(1)
    with pytest.raises(ValueError, match="종류"):
        with gate.slot_sync("unknown"):
            pass
    monkeypatch.setattr(model_gate, "_default_gate", None)
    monkeypatch.setenv("MSDS_MODEL_MAX_INFLIGHT", "2")
    shared = model_gate.get_model_gate()
    assert shared.max_inflight == 2
    assert model_gate.get_model_gate() is shared
    monkeypatch.setattr(model_gate, "_default_gate", None)
    monkeypatch.setenv("MSDS_MODEL_MAX_INFLIGHT", "wrong")
    with pytest.raises(ValueError, match="MSDS_MODEL_MAX_INFLIGHT"):
        model_gate.get_model_gate()


def test_processes_share_limit_and_priority(tmp_path):
    ctx = multiprocessing.get_context("fork")
    gate = ProcessModelGate(1, tmp_path)
    entered = ctx.Queue()
    release = ctx.Event()
    low = ctx.Process(target=_process_call, args=(tmp_path, "explain", entered, release))
    high = ctx.Process(target=_process_call, args=(tmp_path, "extract", entered, release))
    try:
        with gate.slot_sync("extract"):
            low.start()
            _wait_for_requests(tmp_path, 2)
            high.start()
            _wait_for_requests(tmp_path, 3)
            assert entered.empty()
        assert entered.get(timeout=3) == "extract"
        assert entered.empty()
        release.set()
        assert entered.get(timeout=3) == "explain"
    finally:
        release.set()
        for child in (low, high):
            if child.pid:
                child.join(timeout=3)
                if child.is_alive():
                    child.kill()
                    child.join()
    assert low.exitcode == high.exitcode == 0


def test_dead_process_holder_is_reclaimed(tmp_path):
    ctx = multiprocessing.get_context("fork")
    entered = ctx.Queue()
    release = ctx.Event()
    child = ctx.Process(target=_process_call, args=(tmp_path, "extract", entered, release))
    child.start()
    try:
        assert entered.get(timeout=3) == "extract"
        child.kill()
        child.join(timeout=3)
        gate = ProcessModelGate(1, tmp_path)
        with gate.slot_sync("explain"):
            pass
    finally:
        if child.is_alive():
            child.kill()
            child.join()


def test_fork_child_does_not_keep_dead_parent_slot(tmp_path):
    ctx = multiprocessing.get_context("fork")
    entered = ctx.Queue()
    child = ctx.Process(target=_fork_child_while_holding, args=(tmp_path, entered))
    child.start()
    try:
        assert entered.get(timeout=3) > 0
        child.kill()
        gate = ProcessModelGate(1, tmp_path)
        obtained = threading.Event()

        def acquire():
            with gate.slot_sync("explain"):
                obtained.set()

        waiter = threading.Thread(target=acquire, daemon=True)
        waiter.start()
        assert obtained.wait(timeout=1), "자식 프로세스가 죽은 부모의 잠금을 유지함"
        waiter.join(timeout=1)
    finally:
        child.join(timeout=3)


def test_process_gate_async_cancellation_does_not_leak_slot(tmp_path):
    gate = ProcessModelGate(1, tmp_path)

    async def scenario():
        async def wait():
            async with gate.slot("extract"):
                pass

        with gate.slot_sync("explain"):
            task = asyncio.create_task(wait())
            async with asyncio.timeout(2):
                while True:
                    await asyncio.sleep(0.01)
                    with sqlite3.connect(tmp_path / "queue.sqlite3") as db:
                        if db.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 2:
                            break
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            # asyncio.to_thread가 취소를 관찰할 시간을 준다.
            async with asyncio.timeout(2):
                while True:
                    await asyncio.sleep(0.01)
                    with sqlite3.connect(tmp_path / "queue.sqlite3") as db:
                        if db.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 1:
                            break
        with gate.slot_sync("extract"):
            pass

    asyncio.run(scenario())


def test_process_gate_rejects_conflicting_capacities(tmp_path):
    first = ProcessModelGate(1, tmp_path)
    second = ProcessModelGate(2, tmp_path)
    with first.slot_sync("extract"):
        with pytest.raises(ValueError, match="MSDS_MODEL_MAX_INFLIGHT"):
            with second.slot_sync("extract"):
                pass
