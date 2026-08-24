"""Concurrency-safety tests for the ModelDataService dataset-handle lifecycle.

Covers the three failure modes of the legacy cache:
1. concurrent cold opens leaking file descriptors (overwrite without close),
2. LRU eviction closing a dataset while readers are still using it,
3. undefined behaviour from sharing one xarray handle across threads
   (netCDF4/HDF5 and pydap engines are not thread-safe).
"""

from __future__ import annotations

import gc
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import xarray as xr

from app.core.config import Settings
from app.ingestion import netcdf_parser as ncp
from app.models.schemas import DatasetInfo
from app.services import model_service as ms_mod
from app.services.dataset_registry import RegisteredDataset
from app.services.model_service import ModelDataService, UpstreamUnavailableError
from app.testing_utils import write_synthetic_netcdf


class _StubRegistry:
    def __init__(self, entries: dict[str, RegisteredDataset]) -> None:
        self._entries = entries

    def get(self, dataset_id: str) -> RegisteredDataset:
        return self._entries[dataset_id]

    def list(self) -> list[DatasetInfo]:
        return [entry.info for entry in self._entries.values()]


class _OpTracker:
    """Counts ncp.open_dataset/ncp.close_dataset traffic; supports gating."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.opens = 0
        self.closes = 0
        self.in_flight = 0
        self.max_in_flight = 0
        self.gate: threading.Event | None = None
        self.park_hook: Callable[[], None] | None = None
        self.slow_seconds = 0.0
        self.raise_error: BaseException | None = None

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tracker = self
        real_open = ncp.open_dataset
        real_close = ncp.close_dataset

        def fake_open(path: str | Path, engine: str | None = None) -> xr.Dataset:
            with tracker.lock:
                tracker.opens += 1
                tracker.in_flight += 1
                tracker.max_in_flight = max(tracker.max_in_flight, tracker.in_flight)
            try:
                if tracker.park_hook is not None:
                    tracker.park_hook()
                if tracker.gate is not None and not tracker.gate.wait(timeout=10):
                    raise RuntimeError("open gate timed out")
                if tracker.slow_seconds:
                    time.sleep(tracker.slow_seconds)
                with tracker.lock:
                    pending = tracker.raise_error
                if pending is not None:
                    raise pending
                return real_open(path, engine=engine) if engine is not None else real_open(path)
            finally:
                with tracker.lock:
                    tracker.in_flight -= 1

        def fake_close(ds: xr.Dataset | None) -> None:
            if ds is not None:
                with tracker.lock:
                    tracker.closes += 1
            real_close(ds)

        monkeypatch.setattr(ncp, "open_dataset", fake_open)
        monkeypatch.setattr(ncp, "close_dataset", fake_close)


def _make_service(settings: Settings, tmp_path: Path, ids: list[str]) -> ModelDataService:
    entries: dict[str, RegisteredDataset] = {}
    for did in ids:
        path = write_synthetic_netcdf(tmp_path / f"{did}.nc")
        entries[did] = RegisteredDataset(info=DatasetInfo(id=did, title=f"title-{did}"), local_path=path)
    return ModelDataService(_StubRegistry(entries), settings)


def test_single_flight_shares_one_open(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = _OpTracker()
    tracker.slow_seconds = 0.15
    tracker.install(monkeypatch)
    service = _make_service(settings, tmp_path, ["d0"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(service.get_times, "d0") for _ in range(8)]
        results = [future.result(timeout=30) for future in futures]

    assert tracker.opens == 1, "concurrent cold opens must be collapsed into one"
    assert all(result == results[0] for result in results)
    (handle,) = service._handles.values()
    assert handle.refs == 0 and not handle.evicted and not handle.closed


def test_different_datasets_open_concurrently(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = ["d0", "d1", "d2", "d3"]
    quota = len(ids)
    tracker = _OpTracker()
    tracker.install(monkeypatch)
    service = _make_service(settings, tmp_path, ids)

    cond = threading.Condition()
    state = {"inside": 0}
    snapshot: dict[str, int | None] = {"in_flight_at_quota": None}

    def park_until_quota() -> None:
        with cond:
            state["inside"] += 1
            if not cond.wait_for(lambda: state["inside"] >= quota, timeout=30):
                raise AssertionError(f"opens did not overlap: {state['inside']}/{quota} threads inside the opener within 30s")
            if snapshot["in_flight_at_quota"] is None:
                snapshot["in_flight_at_quota"] = tracker.in_flight

    tracker.park_hook = park_until_quota

    with ThreadPoolExecutor(max_workers=quota) as pool:
        futures = {did: pool.submit(service.get_times, did) for did in ids}
        lengths = {did: len(future.result(timeout=60)) for did, future in futures.items()}

    assert all(length > 0 for length in lengths.values())
    assert tracker.opens == quota
    assert snapshot["in_flight_at_quota"] == quota, "all opens must have been simultaneously inside the opener"
    assert tracker.max_in_flight == quota, "independent datasets must not serialise behind a global lock"


def test_eviction_defers_close_until_read_completes(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = ["d0", "d1", "d2", "d3", "d4"]
    tracker = _OpTracker()
    tracker.install(monkeypatch)
    service = _make_service(settings, tmp_path, ids)

    read_started = threading.Event()
    release_read = threading.Event()
    calls = {"n": 0}
    real_gtv = ncp.get_time_values

    def gated_time_values(ds: xr.Dataset) -> list[str]:
        calls["n"] += 1
        if calls["n"] == 1:
            read_started.set()
            assert release_read.wait(timeout=10), "test deadlock: read never released"
        return real_gtv(ds)

    monkeypatch.setattr(ncp, "get_time_values", gated_time_values)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.get_times, "d0")
        assert read_started.wait(timeout=10)
        victim = service._handles["d0"]
        assert victim.refs == 1

        for did in ids[1:]:
            service.get_times(did)

        assert "d0" not in service._handles
        assert victim.evicted
        assert tracker.closes == 0, "eviction closed a dataset while a reader was inside it"

        release_read.set()
        times = future.result(timeout=10)

    assert len(times) > 0
    assert tracker.closes == 1, "deferred close must run once the last lease is released"
    assert len(service.get_times("d0")) > 0
    assert tracker.opens == 6


def test_parallel_reads_match_serial_baseline(settings: Settings, tmp_path: Path) -> None:
    path = write_synthetic_netcdf(tmp_path / "baseline.nc")
    entry = RegisteredDataset(info=DatasetInfo(id="b0", title="t"), local_path=path)

    probe = ncp.open_dataset(path)
    cmap = ncp.CoordinateMap(probe)
    lat_name, lon_name, vertical_name = cmap.lat, cmap.lon, cmap.vertical
    lat = float(probe[str(lat_name)].values[5]) if lat_name is not None else 0.0
    lon = float(probe[str(lon_name)].values[6]) if lon_name is not None else 0.0
    depths = [float(v) for v in probe[str(vertical_name)].values] if vertical_name is not None else []
    ncp.close_dataset(probe)
    assert lat_name is not None and lon_name is not None and depths

    ops: list[Callable[[ModelDataService], object]] = [
        lambda svc: svc.read_slice("b0", "temperature", time_index=0, depth_meters=depths[1], bbox=None).model_dump(),
        lambda svc: svc.read_slice("b0", "temperature", time_index=None, depth_meters=None, bbox=None).model_dump(),
        lambda svc: svc.read_profile("b0", "temperature", latitude=lat, longitude=lon, time_index=0).model_dump(),
        lambda svc: svc.read_point("b0", ["temperature", "salinity"], latitude=lat, longitude=lon, time_index=0, depth_meters=depths[2]).model_dump(),
        lambda svc: svc.read_point("b0", ["temperature"], latitude=lat, longitude=lon, time_index=None, depth_meters=None).model_dump(),
    ]

    serial = ModelDataService(_StubRegistry({"b0": entry}), settings)
    expected = [op(serial) for op in ops]
    parallel = ModelDataService(_StubRegistry({"b0": entry}), settings)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {(r, i): pool.submit(op, parallel) for r in range(3) for i, op in enumerate(ops)}
        for (round_, op_index), future in futures.items():
            assert future.result(timeout=60) == expected[op_index], f"mismatch round={round_} op={op_index}"


def test_open_failure_broadcast_then_retry_succeeds(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = _OpTracker()
    tracker.slow_seconds = 0.05
    tracker.install(monkeypatch)
    service = _make_service(settings, tmp_path, ["f0"])
    tracker.raise_error = RuntimeError("boom")

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(service.get_times, "f0") for _ in range(6)]
        errors = []
        for future in futures:
            with pytest.raises(RuntimeError, match="boom"):
                future.result(timeout=30)
            try:
                future.result(timeout=30)
            except RuntimeError as exc:
                errors.append(str(exc))
    assert errors and all(message == "boom" for message in errors), "every caller must see the identical controlled failure"

    tracker.raise_error = None
    assert len(service.get_times("f0")) > 0, "a subsequent attempt must retry cleanly"
    (handle,) = service._handles.values()
    assert handle.refs == 0


def test_resource_bounds_across_open_evict_cycles(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import psutil
    except ImportError:
        psutil = None

    ids = [f"c{i}" for i in range(8)]
    tracker = _OpTracker()
    tracker.install(monkeypatch)
    service = _make_service(settings, tmp_path, ids)

    baseline_handles: int | None = None
    process = psutil.Process() if psutil is not None else None
    if process is not None:
        baseline_handles = getattr(process, "num_fds", process.num_handles)()

    for _ in range(5):
        for did in ids:
            assert len(service.get_times(did)) > 0

    assert len(service._handles) <= service._max_open
    assert tracker.opens - tracker.closes == len(service._handles), "every open must be paired with exactly one close or stay cached"

    service.close_all()
    assert not service._handles
    assert tracker.closes == tracker.opens

    if process is not None and baseline_handles is not None:
        gc.collect()
        growth = getattr(process, "num_fds", process.num_handles)() - baseline_handles
        assert growth < 50, f"descriptor leak suspected: grew by {growth}"


def test_waiter_timeout_is_bounded_and_non_fatal(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ms_mod, "_OPEN_WAIT_TIMEOUT", 0.05)
    tracker = _OpTracker()
    tracker.install(monkeypatch)
    service = _make_service(settings, tmp_path, ["w0"])
    tracker.gate = threading.Event()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.get_times, "w0")
        deadline = time.monotonic() + 5
        while tracker.opens == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        with pytest.raises(UpstreamUnavailableError, match="timed out"):
            service.get_times("w0")
        tracker.gate.set()
        assert len(future.result(timeout=10)) > 0

    tracker.gate = None
    assert len(service.get_times("w0")) > 0


def test_close_failures_are_logged_not_raised(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    ids = ["x0", "x1", "x2", "x3", "x4"]
    real_close = ncp.close_dataset

    def exploding_close(ds: xr.Dataset | None) -> None:
        real_close(ds)
        raise RuntimeError("hdf5 boom")

    monkeypatch.setattr(ncp, "close_dataset", exploding_close)
    service = _make_service(settings, tmp_path, ids)

    with caplog.at_level(logging.WARNING, logger="echoshield.model"):
        assert len(service.get_times("x0")) > 0
        service.close_all()
        assert len(service.get_times("x0")) > 0
        for did in ids[1:]:
            assert len(service.get_times(did)) > 0

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING and "failed to close" in record.getMessage()]
    assert warnings, "close failures must be surfaced through warning logs, never swallowed silently"
    assert service.list_datasets()


def test_close_all_during_open_does_not_recache_or_leak(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = _OpTracker()
    tracker.install(monkeypatch)
    service = _make_service(settings, tmp_path, ["s0"])
    tracker.gate = threading.Event()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.get_times, "s0")
        deadline = time.monotonic() + 5
        while tracker.opens == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert tracker.opens == 1

        service.close_all()
        assert not service._handles

        tracker.gate.set()
        assert len(future.result(timeout=10)) > 0, "the in-flight reader must still complete with valid data"

    handle_state = service._handles.get("s0")
    assert handle_state is None, "an open completing after close_all must not repopulate the cache"
    assert tracker.closes == 1, "the uncached handle must be closed exactly once, at its final release"
    assert not service._flights


def test_reader_exception_releases_lease_and_lock(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = _OpTracker()
    tracker.install(monkeypatch)
    service = _make_service(settings, tmp_path, ["e0"])
    real_gtv = ncp.get_time_values
    calls = {"n": 0}

    def flaky_time_values(ds: xr.Dataset) -> list[str]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient read failure")
        return real_gtv(ds)

    monkeypatch.setattr(ncp, "get_time_values", flaky_time_values)

    with pytest.raises(RuntimeError, match="transient"):
        service.get_times("e0")

    handle = service._handles["e0"]
    assert handle.refs == 0 and not handle.closed
    assert len(service.get_times("e0")) > 0
    assert tracker.opens == 1 and calls["n"] == 2
