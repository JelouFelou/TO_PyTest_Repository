import asyncio
import pytest

from epc import traffic as traffic_module
from epc.db import EPCRepository
from epc.models import BearerConfig, ThroughputStats
from epc.traffic import TrafficGeneratorManager, get_traffic_manager


# Checks that a new manager starts without any active traffic tasks.
def test_manager_starts_without_running_traffic(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    manager = TrafficGeneratorManager(repo)

    assert manager.tasks == {}
    assert not manager.is_running(1, 1)


# Checks that starting traffic marks the bearer as running.
def test_start_traffic_marks_bearer_as_running(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(bearer_id=1, protocol="udp", target_bps=100_000)

    manager.start(1, bearer)

    assert manager.is_running(1, 1)

    manager.stop_all()


# Checks that the manager tracks traffic by exact UE ID and bearer ID.
def test_is_running_checks_exact_ue_and_bearer(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(bearer_id=1, protocol="udp", target_bps=100_000)

    manager.start(1, bearer)

    assert manager.is_running(1, 1)
    assert not manager.is_running(1, 2)
    assert not manager.is_running(2, 1)

    manager.stop_all()


# Checks that the same bearer ID can run independently for different UEs.
def test_same_bearer_id_can_run_for_different_ues(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)
    repo.attach_ue(2)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(bearer_id=1, protocol="tcp", target_bps=100_000)

    manager.start(1, bearer)
    manager.start(2, bearer)

    assert manager.is_running(1, 1)
    assert manager.is_running(2, 1)

    manager.stop_all()


# Checks that starting traffic requires a fully configured bearer.
def test_start_traffic_requires_configuration(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(bearer_id=1)

    with pytest.raises(ValueError, match="Bearer not configured for traffic"):
        manager.start(1, bearer)

    manager.stop_all()


# Checks that missing protocol prevents traffic from starting.
def test_start_traffic_requires_protocol(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(bearer_id=1, target_bps=100_000)

    with pytest.raises(ValueError, match="Bearer not configured for traffic"):
        manager.start(1, bearer)

    assert not manager.is_running(1, 1)


# Checks that missing target prevents traffic from starting.
def test_start_traffic_requires_target_bps(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(bearer_id=1, protocol="udp")

    with pytest.raises(ValueError, match="Bearer not configured for traffic"):
        manager.start(1, bearer)

    assert not manager.is_running(1, 1)


# Checks that the same traffic cannot be started twice.
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


# Checks that "stop_all" stops all running tasks.
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


# Checks that "stop_unknown_traffic_is_noop" is a safe.
def test_stop_unknown_traffic_is_noop(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    manager = TrafficGeneratorManager(repo)

    manager.stop(1, 1)

    assert manager.tasks == {}
    assert not manager.is_running(1, 1)


# Checks that "stop_all" is safe when no traffic is running.
def test_stop_all_without_running_traffic_is_noop(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    manager = TrafficGeneratorManager(repo)

    manager.stop_all()

    assert manager.tasks == {}


# Checks that stopping one bearer does not stop the others.
def test_stopping_one_bearer_keeps_other_running(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    manager.start(1, BearerConfig(bearer_id=1, protocol="udp", target_bps=100_000))
    manager.start(1, BearerConfig(bearer_id=2, protocol="tcp", target_bps=200_000))

    manager.stop(1, 1)

    assert not manager.is_running(1, 1)
    assert manager.is_running(1, 2)

    manager.stop_all()


# Checks that get_traffic_manager returns the same singleton manager.
def test_get_traffic_manager_returns_singleton(tmp_path, monkeypatch):
    monkeypatch.setattr(traffic_module, "traffic_manager", None)

    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager_a = get_traffic_manager(repo)
    manager_b = get_traffic_manager(repo)

    assert manager_a is manager_b
    assert manager_a.repo is repo

    manager_a.stop_all()


# Checks that one simulation iteration creates and updates stats.
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


# Checks that simulation adds bytes to existing stats.
def test_simulated_bearer_accumulates_existing_stats(tmp_path, monkeypatch):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    bearer_id = 1
    repo.update_stats(
        1,
        ThroughputStats(
            bearer_id=bearer_id,
            ue_id=1,
            bytes_tx=123,
            bytes_rx=456,
            start_ts=10.0,
        ),
    )

    manager = TrafficGeneratorManager(repo)
    target_bps = 16_000

    async def run_once():
        event = asyncio.Event()
        pause = asyncio.Event()

        async def fake_sleep(delay):
            event.set()
            await pause.wait()

        monkeypatch.setattr(traffic_module.asyncio, "sleep", fake_sleep)

        task = asyncio.create_task(
            manager._run_simulated_bearer(1, bearer_id, target_bps, "tcp")
        )

        await asyncio.wait_for(event.wait(), timeout=1.0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run_once())

    stats = repo.get_ue(1).stats[bearer_id]
    assert stats.bytes_tx == 123 + target_bps // 8
    assert stats.bytes_rx == 456 + target_bps // 8
    assert stats.start_ts == 10.0
    assert stats.last_update_ts is not None
    assert stats.protocol == "tcp"
    assert stats.target_bps == target_bps
