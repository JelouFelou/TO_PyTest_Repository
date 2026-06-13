"""Layer 1 tests: models (validation, normalization, conversion, defaults).

Scope (per Testing Scope Guide):
- field ranges
- protocol constraints
- cross-field validation
- throughput conversion to canonical target_bps
- default model state
"""

import pytest
from pydantic import ValidationError

from epc.models import (
    BearerConfig,
    StartTrafficRequest,
    UEState,
)


# field ranges -------------------------------------------------------------- #
def test_bearer_id_in_range_ok():
    assert BearerConfig(bearer_id=5).bearer_id == 5


def test_bearer_id_out_of_range_rejected():
    with pytest.raises(ValidationError):
        BearerConfig(bearer_id=10)


# protocol constraints ------------------------------------------------------ #
def test_invalid_protocol_rejected():
    with pytest.raises(ValidationError):
        BearerConfig(bearer_id=1, protocol="http")


# cross-field validation ---------------------------------------------------- #
def test_exactly_one_throughput_required():
    with pytest.raises(ValidationError):
        StartTrafficRequest(protocol="tcp", Mbps=1, kbps=500)


# throughput conversion to canonical target_bps ---------------------------- #
def test_mbps_converts_to_target_bps():
    assert StartTrafficRequest(protocol="tcp", Mbps=1).target_bps() == 1_000_000


# default model state ------------------------------------------------------- #
def test_bearer_defaults():
    cfg = BearerConfig(bearer_id=3)
    assert cfg.protocol is None and cfg.target_bps is None and cfg.active is False


def test_ue_state_defaults_to_empty_dicts():
    ue = UEState(ue_id=1)
    assert ue.bearers == {} and ue.stats == {}
