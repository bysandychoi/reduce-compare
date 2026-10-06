"""병렬 크기 탐색의 결과 순서와 조기 종료를 검증한다 (T112)."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Lock
from time import sleep
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.core import pipeline


def _attempt(size, score):
    return SimpleNamespace(size=size, score=score, distribution=score,
                           correlation=score, structure=score)


def test_parallel_search_keeps_smallest_passing_candidate(monkeypatch):
    candidates = [100, 200, 300, 400]
    gate = Barrier(2)
    called = set()

    def fake_run_once(_df, _x, _columns, _selected, _method, size, _seed):
        called.add(size)
        gate.wait(timeout=2)
        return _attempt(size, {100: 80, 200: 90, 300: 99, 400: 99}[size])

    monkeypatch.setattr(pipeline, "size_candidates", lambda _total: candidates)
    monkeypatch.setattr(pipeline, "run_once", fake_run_once)

    chosen, curve = pipeline.search_size(pd.DataFrame(), np.zeros((10, 1)), [], [],
                                         target=85, workers=2)

    assert called == {100, 200}  # 두 후보 동시 실행, 다음 배치는 시작하지 않는다
    assert chosen.size == 200
    assert [point["size"] for point in curve] == [100, 200]


def test_parallel_search_returns_best_when_target_is_unreachable(monkeypatch):
    candidates = [100, 200, 300]
    scores = {100: 60, 200: 70, 300: 55}
    monkeypatch.setattr(pipeline, "size_candidates", lambda _total: candidates)
    monkeypatch.setattr(
        pipeline, "run_once",
        lambda _df, _x, _columns, _selected, _method, size, _seed: _attempt(size, scores[size]),
    )

    args = (pd.DataFrame(), np.zeros((10, 1)), [], [])
    serial, serial_curve = pipeline.search_size(*args, target=85, workers=1)
    parallel, parallel_curve = pipeline.search_size(*args, target=85, workers=2)

    assert serial.size == parallel.size == 200
    assert serial.score == parallel.score == 70
    assert serial_curve == parallel_curve
    assert [point["size"] for point in parallel_curve] == candidates


@pytest.mark.parametrize("workers", [0, pipeline.SEARCH_WORKERS + 1])
def test_search_rejects_out_of_range_worker_count(workers):
    with pytest.raises(ValueError, match="worker 수는 1~2"):
        pipeline.search_size(pd.DataFrame(), np.zeros((10, 1)), [], [], workers=workers)


def test_concurrent_batches_serialize_global_threadpool_limits(monkeypatch):
    state_lock = Lock()
    active, maximum = 0, 0

    @contextmanager
    def fake_limits(**_kwargs):
        nonlocal active, maximum
        with state_lock:
            active += 1
            maximum = max(maximum, active)
        sleep(0.02)
        try:
            yield
        finally:
            with state_lock:
                active -= 1

    monkeypatch.setattr(pipeline, "threadpool_limits", fake_limits)
    monkeypatch.setattr(
        pipeline, "run_once",
        lambda _df, _x, _columns, _selected, _method, size, _seed: _attempt(size, 1),
    )
    args = (pd.DataFrame(), np.zeros((10, 1)), [], [], "cluster_actual", [100, 200], 0)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(pipeline._run_candidate_batch, *args) for _ in range(2)]
        [future.result() for future in futures]

    assert maximum == 1
    assert active == 0
