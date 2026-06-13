import asyncio
import pytest

from epc import traffic as traffic_module
from epc.db import EPCRepository
from epc.models import BearerConfig
from epc.traffic import TrafficGeneratorManager, get_traffic_manager


def test_start_traffic_requires_configuration(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(bearer_id=1)

    with pytest.raises(ValueError, match="Bearer not configured"):
        manager.start(1, bearer)

    manager.stop_all()


def test_starting_traffic_twice_raises(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(bearer_id=1, protocol="tcp", target_bps=800_000)

    manager.start(1, bearer)
    assert manager.is_running(1, 1)

    with pytest.raises(ValueError, match="Traffic already running"):
        manager.start(1, bearer)

    manager.stop(1, 1)
    assert not manager.is_running(1, 1)


def test_stop_all_cancels_all_running_tasks(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    manager.start(1, BearerConfig(bearer_id=1, protocol="udp", target_bps=100_000))
    manager.start(1, BearerConfig(bearer_id=2, protocol="tcp", target_bps=200_000))

    assert manager.is_running(1, 1)
    assert manager.is_running(1, 2)

    manager.stop_all()

    assert not manager.is_running(1, 1)
    assert not manager.is_running(1, 2)


def test_get_traffic_manager_returns_singleton(tmp_path, monkeypatch):
    monkeypatch.setattr(traffic_module, "traffic_manager", None)

    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager_a = get_traffic_manager(repo)
    manager_b = get_traffic_manager(repo)

    assert manager_a is manager_b
    assert manager_a.repo is repo

    manager_a.stop_all()


def test_simulated_bearer_updates_stats_once(tmp_path, monkeypatch):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer_id = 1
    target_bps = 8_000

    async def run_once():
        event = asyncio.Event()
        pause = asyncio.Event()

        async def fake_sleep(delay):
            event.set()
            await pause.wait()

        monkeypatch.setattr(traffic_module.asyncio, "sleep", fake_sleep)

        task = asyncio.create_task(
            manager._run_simulated_bearer(1, bearer_id, target_bps, "udp")
        )

        await asyncio.wait_for(event.wait(), timeout=1.0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run_once())

    stats = repo.get_ue(1).stats[bearer_id]
    assert stats.protocol == "udp"
    assert stats.target_bps == target_bps
    assert stats.bytes_tx == target_bps // 8
    assert stats.bytes_rx == target_bps // 8
    assert stats.start_ts is not None
    assert stats.last_update_ts is not None
