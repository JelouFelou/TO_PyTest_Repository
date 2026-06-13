"""Layer 2 tests: repository (SQLite state and invariants).

Scope (per Testing Scope Guide):
- attach/get/list/detach UE flows
- default bearer and duplicate handling
- bearer add/update/delete behavior
- persisted updates and state cleanup
- statistics storage and replacement
- reset behavior and database persistence
"""

import pytest

from epc.db import EPCRepository
from epc.models import BearerConfig, ThroughputStats


@pytest.fixture
def repo(tmp_path):
    """Return a repository backed by a fresh database for each test."""
    return EPCRepository(str(tmp_path / "epc-test.db"))


def test_attach_ue_persists_state_and_creates_default_bearer(repo):
    repo.attach_ue(1)

    state = repo.get_ue(1)

    assert repo.ue_exists(1) is True
    assert state.ue_id == 1
    assert set(state.bearers) == {9}
    assert state.bearers[9] == BearerConfig(bearer_id=9)
    assert state.stats == {}


def test_attaching_duplicate_ue_raises_error(repo):
    repo.attach_ue(1)

    with pytest.raises(ValueError, match="UE already attached"):
        repo.attach_ue(1)


def test_list_ues_returns_ids_in_ascending_order(repo):
    for ue_id in (10, 2, 7):
        repo.attach_ue(ue_id)

    assert list(repo.list_ues()) == [2, 7, 10]


def test_detach_ue_removes_its_state(repo):
    repo.attach_ue(1)

    repo.detach_ue(1)

    assert repo.ue_exists(1) is False
    with pytest.raises(ValueError, match="UE not found"):
        repo.get_ue(1)


def test_detaching_unknown_ue_raises_error(repo):
    with pytest.raises(ValueError, match="UE not found"):
        repo.detach_ue(99)


def test_add_bearer_persists_it(repo):
    repo.attach_ue(1)

    repo.add_bearer(1, 2)

    assert set(repo.get_ue(1).bearers) == {2, 9}


def test_adding_duplicate_bearer_raises_error(repo):
    repo.attach_ue(1)
    repo.add_bearer(1, 2)

    with pytest.raises(ValueError, match="Bearer already exists"):
        repo.add_bearer(1, 2)


def test_adding_bearer_to_unknown_ue_raises_error(repo):
    with pytest.raises(ValueError, match="UE not found"):
        repo.add_bearer(99, 2)


def test_update_bearer_persists_configuration(repo):
    repo.attach_ue(1)
    bearer = BearerConfig(
        bearer_id=9,
        protocol="udp",
        target_bps=1_000_000,
        active=True,
    )

    repo.update_bearer(1, bearer)

    assert repo.get_ue(1).bearers[9] == bearer


def test_delete_bearer_removes_bearer_and_its_stats(repo):
    repo.attach_ue(1)
    repo.add_bearer(1, 2)
    repo.update_stats(
        1,
        ThroughputStats(
            bearer_id=2,
            ue_id=1,
            bytes_tx=100,
            bytes_rx=200,
        ),
    )

    repo.delete_bearer(1, 2)

    state = repo.get_ue(1)
    assert 2 not in state.bearers
    assert 2 not in state.stats


def test_default_bearer_cannot_be_deleted(repo):
    repo.attach_ue(1)

    with pytest.raises(ValueError, match="Cannot remove default bearer"):
        repo.delete_bearer(1, 9)

    assert 9 in repo.get_ue(1).bearers


def test_deleting_unknown_bearer_raises_error(repo):
    repo.attach_ue(1)

    with pytest.raises(ValueError, match="Bearer not found"):
        repo.delete_bearer(1, 2)


def test_update_stats_persists_and_replaces_counters(repo):
    repo.attach_ue(1)
    first = ThroughputStats(
        bearer_id=9,
        ue_id=1,
        bytes_tx=100,
        bytes_rx=200,
        protocol="tcp",
        target_bps=800,
    )
    updated = first.model_copy(update={"bytes_tx": 300, "bytes_rx": 400})

    repo.update_stats(1, first)
    repo.update_stats(1, updated)

    assert repo.get_ue(1).stats[9] == updated


def test_update_missing_bearer_raises_error(repo):
    repo.attach_ue(1)

    with pytest.raises(ValueError, match="Bearer not found"):
        repo.update_bearer(1, BearerConfig(bearer_id=2, protocol="tcp"))


def test_update_stats_for_missing_bearer_raises_error(repo):
    repo.attach_ue(1)
    stats = ThroughputStats(bearer_id=2, ue_id=1, bytes_tx=100)

    with pytest.raises(ValueError, match="Bearer not found"):
        repo.update_stats(1, stats)


def test_update_stats_with_mismatched_ue_id_raises_error(repo):
    repo.attach_ue(1)
    stats = ThroughputStats(bearer_id=9, ue_id=2, bytes_tx=100)

    with pytest.raises(ValueError, match="UE ID mismatch"):
        repo.update_stats(1, stats)


def test_reset_all_removes_every_ue(repo):
    for ue_id in (1, 2, 3):
        repo.attach_ue(ue_id)

    repo.reset_all()

    assert list(repo.list_ues()) == []
