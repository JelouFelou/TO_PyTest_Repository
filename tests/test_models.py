"""Layer 1 tests - models (epc/models.py).

Scope (per Testing Scope Guide):
- field ranges
- protocol constraints
- cross-field validation (exactly one throughput value)
- throughput conversion to canonical target_bps
- default model state
"""

import pytest
from pydantic import ValidationError

from epc.models import (
    AddBearerRequest,
    AttachUERequest,
    BearerConfig,
    StartTrafficRequest,
    ThroughputStats,
    UEState,
)

# - field ranges

# bearer_id w dozwolonym zakresie 1-9 jest akceptowany
@pytest.mark.parametrize("bearer_id", [1, 5, 9])
def test_bearer_id_in_range_ok(bearer_id):
    assert BearerConfig(bearer_id=bearer_id).bearer_id == bearer_id


# bearer_id poza zakresem 1-9 jest odrzucany
@pytest.mark.parametrize("bearer_id", [0, -1, 10, 1000])
def test_bearer_id_out_of_range_rejected(bearer_id):
    with pytest.raises(ValidationError):
        BearerConfig(bearer_id=bearer_id)


# ue_id w dozwolonym zakresie 1-100 jest akceptowany
@pytest.mark.parametrize("ue_id", [1, 50, 100])
def test_ue_id_in_range_ok(ue_id):
    assert UEState(ue_id=ue_id).ue_id == ue_id


# ue_id poza zakresem 1-100 jest odrzucany
@pytest.mark.parametrize("ue_id", [0, -1, 101])
def test_ue_id_out_of_range_rejected(ue_id):
    with pytest.raises(ValidationError):
        UEState(ue_id=ue_id)


# request attach respektuje zakres ue_id
def test_attach_request_out_of_range_rejected():
    with pytest.raises(ValidationError):
        AttachUERequest(ue_id=0)


# request add-bearer respektuje zakres bearer_id
def test_add_bearer_request_out_of_range_rejected():
    with pytest.raises(ValidationError):
        AddBearerRequest(bearer_id=10)


# - protocol constraints

# tylko 'tcp' i 'udp' sa dozwolone
@pytest.mark.parametrize("protocol", ["tcp", "udp"])
def test_protocol_allowed(protocol):
    assert BearerConfig(bearer_id=1, protocol=protocol).protocol == protocol


# wszystko inne (zla wielkosc liter, inny protokol, spacje) jest odrzucane
@pytest.mark.parametrize("protocol", ["TCP", "http", "UDP", "", "tcp ", " tcp"])
def test_protocol_invalid_rejected(protocol):
    with pytest.raises(ValidationError):
        BearerConfig(bearer_id=1, protocol=protocol)


# - cross-field validation (exactly one throughput value)

# poprawnie: dokladnie jedna wartosc przepustowosci
@pytest.mark.parametrize("kwargs", [{"Mbps": 1}, {"kbps": 1}, {"bps": 1}])
def test_exactly_one_throughput_ok(kwargs):
    StartTrafficRequest(protocol="tcp", **kwargs)


# brak jakiejkolwiek wartosci przepustowosci jest odrzucany
def test_no_throughput_rejected():
    with pytest.raises(ValidationError):
        StartTrafficRequest(protocol="tcp")


# podanie dwoch lub trzech wartosci naraz jest odrzucane
@pytest.mark.parametrize("kwargs", [
    {"Mbps": 1, "kbps": 1},
    {"Mbps": 1, "bps": 1},
    {"Mbps": 1, "kbps": 1, "bps": 1},
])
def test_multiple_throughput_rejected(kwargs):
    with pytest.raises(ValidationError):
        StartTrafficRequest(protocol="udp", **kwargs)


# - throughput conversion to canonical target_bps

# Mbps -> bps (x1 000 000), wartosci calkowite
def test_mbps_integer_conversion():
    assert StartTrafficRequest(protocol="tcp", Mbps=5).target_bps() == 5_000_000


# kbps -> bps (x1 000)
def test_kbps_conversion():
    assert StartTrafficRequest(protocol="tcp", kbps=250).target_bps() == 250_000


# bps -> bps (bez zmian)
def test_bps_conversion():
    assert StartTrafficRequest(protocol="tcp", bps=12345).target_bps() == 12345


# - default model state

# swiezy BearerConfig ma puste/falszywe pola domyslne
def test_bearer_default_state():
    cfg = BearerConfig(bearer_id=3)
    assert cfg.protocol is None and cfg.target_bps is None and cfg.active is False


# nowy UEState startuje z pustymi slownikami bearers i stats
def test_ue_state_default_empty_dicts():
    ue = UEState(ue_id=1)
    assert ue.bearers == {} and ue.stats == {}


# jawne None dla bearers/stats jest normalizowane do {}
def test_ue_state_none_normalized_to_empty():
    ue = UEState(ue_id=1, bearers=None, stats=None)
    assert ue.bearers == {} and ue.stats == {}


# ThroughputStats ma zerowe liczniki i puste pola opcjonalne
def test_throughput_stats_default_state():
    s = ThroughputStats(bearer_id=1, ue_id=1)
    assert s.bytes_tx == 0 and s.bytes_rx == 0 and s.protocol is None
