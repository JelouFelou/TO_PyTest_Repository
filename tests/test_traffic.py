import pytest

from epc import traffic as traffic_module
from epc.db import EPCRepository
from epc.models import BearerConfig
from epc.traffic import TrafficGeneratorManager, get_traffic_manager


MAX_UE_TARGET_BPS = 100_000_000


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


# Checks that missing target prevents traffic from starting.
def test_start_traffic_requires_target_bps(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(bearer_id=1, protocol="udp")

    with pytest.raises(ValueError, match="Bearer not configured for traffic"):
        manager.start(1, bearer)

    assert not manager.is_running(1, 1)


# Checks that traffic above 100 Mbps per UE is rejected.
def test_start_traffic_rejects_speed_above_100_mbps(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(
        bearer_id=1,
        protocol="tcp",
        target_bps=MAX_UE_TARGET_BPS + 1,
    )

    with pytest.raises(ValueError):
        manager.start(1, bearer)

    assert not manager.is_running(1, 1)


# Checks that negative traffic speed is rejected.
def test_start_traffic_rejects_negative_speed(tmp_path):
    repo = EPCRepository(db_path=str(tmp_path / "repo.db"))
    repo.attach_ue(1)

    manager = TrafficGeneratorManager(repo)
    bearer = BearerConfig(bearer_id=1, protocol="udp", target_bps=-1)

    with pytest.raises(ValueError):
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