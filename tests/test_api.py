"""Layer 4 tests: HTTP API (FastAPI endpoints via TestClient).

Scope (per Testing Scope Guide + README "Features"):
- requirement boundaries (UE 1..100, bearer 1..9, protocol tcp|udp, one unit)
- happy-path responses for main routes
- consistent error status behavior (400 domain vs 422 validation)
- response body shape and state transitions

The final section contains bug-revealing tests (adversarial / boundary inputs)
that are DESIGNED TO FAIL on the current code: each asserts the behavior
required by the spec (README) while the implementation violates it.
"""

import os
import sys

# udostępnij katalog główny projektu, aby zaimportować `main` oraz `epc` ze źródeł
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import epc.traffic as traffic
from epc.api import get_repo
from epc.db import EPCRepository
from main import app


@pytest.fixture
def client(tmp_path):
    # izolowane repozytorium na tymczasowym pliku SQLite + świeży menedżer ruchu
    repo = EPCRepository(str(tmp_path / "test.db"))
    app.dependency_overrides[get_repo] = lambda: repo
    traffic.traffic_manager = None
    c = TestClient(app)
    yield c
    tm = traffic.traffic_manager
    if tm:
        tm.stop_all()
    traffic.traffic_manager = None
    app.dependency_overrides.clear()


# happy-path & contract (15 funkcji) ---------------------------------------- #
def test_root_returns_running_message(client):
    # sprawdza endpoint zdrowia "/" zwracający komunikat o działaniu serwisu
    resp = client.get("/")
    assert resp.status_code == 200 and resp.json() == {"message": "EPC Simulator running"}


def test_list_ues_returns_attached_ids(client):
    # lista UE zwraca posortowane identyfikatory podłączonych UE
    client.post("/ues", json={"ue_id": 2})
    client.post("/ues", json={"ue_id": 1})
    assert client.get("/ues").json() == {"ues": [1, 2]}


@pytest.mark.parametrize("ue_id,expected", [(0, 422), (1, 200), (100, 200), (101, 422)])
def test_attach_ue_id_boundaries(client, ue_id, expected):
    # wymaganie README: UE w zakresie 1..100 — granice i wartości tuż poza
    assert client.post("/ues", json={"ue_id": ue_id}).status_code == expected


def test_attach_creates_default_bearer_9(client):
    # po podłączeniu UE ma automatycznie domyślny bearer 9 (pokrywa też GET /ues/{id})
    client.post("/ues", json={"ue_id": 1})
    state = client.get("/ues/1").json()
    assert "9" in state["bearers"]


def test_attach_duplicate_ue_returns_400(client):
    # ponowne podłączenie tego samego UE to błąd domenowy (400)
    client.post("/ues", json={"ue_id": 1})
    resp = client.post("/ues", json={"ue_id": 1})
    assert resp.status_code == 400


def test_detach_ue_success(client):
    # odłączenie istniejącego UE zwraca status "detached"
    client.post("/ues", json={"ue_id": 1})
    resp = client.delete("/ues/1")
    assert resp.status_code == 200 and resp.json() == {"status": "detached", "ue_id": 1}


@pytest.mark.parametrize("bearer_id,expected", [(0, 422), (1, 200), (10, 422)])
def test_add_bearer_id_boundaries(client, bearer_id, expected):
    # wymaganie README: bearer w zakresie 1..9 — wartość poprawna i poza zakresem
    client.post("/ues", json={"ue_id": 1})
    assert client.post("/ues/1/bearers", json={"bearer_id": bearer_id}).status_code == expected


def test_delete_bearer_success(client):
    # usunięcie wcześniej dodanego bearera zwraca status "bearer_deleted"
    client.post("/ues", json={"ue_id": 1})
    client.post("/ues/1/bearers", json={"bearer_id": 1})
    resp = client.delete("/ues/1/bearers/1")
    assert resp.status_code == 200 and resp.json()["status"] == "bearer_deleted"


def test_delete_default_bearer_9_returns_400(client):
    # domyślnego bearera 9 nie wolno usunąć (400)
    client.post("/ues", json={"ue_id": 1})
    assert client.delete("/ues/1/bearers/9").status_code == 400


@pytest.mark.parametrize("protocol,expected", [("tcp", 200), ("udp", 200), ("http", 422)])
def test_start_traffic_protocol_constraint(client, protocol, expected):
    # wymaganie README: protokół ograniczony do tcp|udp — inne odrzucane (422)
    client.post("/ues", json={"ue_id": 1})
    resp = client.post("/ues/1/bearers/9/traffic", json={"protocol": protocol, "Mbps": 1})
    assert resp.status_code == expected


@pytest.mark.parametrize("body,status,bps", [
    ({"protocol": "tcp", "Mbps": 1}, 200, 1_000_000),
    ({"protocol": "tcp", "kbps": 1000}, 200, 1_000_000),
    ({"protocol": "tcp", "bps": 1000}, 200, 1000),
    ({"protocol": "tcp"}, 422, None),
    ({"protocol": "tcp", "Mbps": 1, "kbps": 5}, 422, None),
])
def test_start_traffic_throughput_units(client, body, status, bps):
    # wymaganie README: dokładnie jedna jednostka Mbps/kbps/bps, normalizowana do target_bps
    client.post("/ues", json={"ue_id": 1})
    resp = client.post("/ues/1/bearers/9/traffic", json=body)
    assert resp.status_code == status
    if bps is not None:
        assert resp.json()["target_bps"] == bps


def test_stop_traffic_success(client):
    # zatrzymanie ruchu na bearerze zwraca status "traffic_stopped"
    client.post("/ues", json={"ue_id": 1})
    resp = client.delete("/ues/1/bearers/9/traffic")
    assert resp.status_code == 200 and resp.json()["status"] == "traffic_stopped"


def test_traffic_stats_without_traffic_returns_zeros(client):
    # odczyt statystyk per bearer bez uruchomionego ruchu zwraca zerowe przepływności
    client.post("/ues", json={"ue_id": 1})
    body = client.get("/ues/1/bearers/9/traffic").json()
    assert body["tx_bps"] == 0 and body["rx_bps"] == 0 and body["duration"] == 0


def test_traffic_stats_after_start_reports_config(client):
    # po starcie ruchu statystyki per bearer raportują protokół i docelową przepływność
    client.post("/ues", json={"ue_id": 1})
    client.post("/ues/1/bearers/9/traffic", json={"protocol": "tcp", "Mbps": 1})
    body = client.get("/ues/1/bearers/9/traffic").json()
    assert body["protocol"] == "tcp" and body["target_bps"] == 1_000_000


def test_ues_stats_aggregate_all(client):
    # agregacja globalna zwraca zakres 'all' i liczbę podłączonych UE
    client.post("/ues", json={"ue_id": 1})
    body = client.get("/ues/stats").json()
    assert body["scope"] == "all" and body["ue_count"] == 1


def test_ues_stats_single_ue_scope(client):
    # agregacja dla jednego UE zwraca zakres 'ue:{id}'
    client.post("/ues", json={"ue_id": 1})
    body = client.get("/ues/stats", params={"ue_id": 1}).json()
    assert body["scope"] == "ue:1" and body["ue_count"] == 1


def test_ues_stats_unknown_ue_returns_400(client):
    # agregacja statystyk dla nieistniejącego UE to błąd domenowy (400)
    assert client.get("/ues/stats", params={"ue_id": 5}).status_code == 400


def test_reset_clears_all_state(client):
    # reset usuwa cały stan — po nim lista UE jest ponownie pusta (pokrywa też GET /ues)
    client.post("/ues", json={"ue_id": 1})
    assert client.post("/reset").json() == {"status": "reset"}
    assert client.get("/ues").json() == {"ues": []}


# bug-revealing tests (oczekiwane FAIL — ujawniają realne defekty) ---------- #
def test_negative_throughput_is_rejected(client):
    # BUG A: ujemna przepustowość powinna być odrzucona (4xx), a jest akceptowana (200)
    client.post("/ues", json={"ue_id": 1})
    resp = client.post("/ues/1/bearers/9/traffic", json={"protocol": "tcp", "Mbps": -5})
    assert resp.status_code >= 400


def test_failed_traffic_start_does_not_activate_bearer(client):
    # BUG B: nieudane uruchomienie ruchu (400) nie powinno pozostawiać bearera jako aktywnego
    client.post("/ues", json={"ue_id": 1})
    resp = client.post("/ues/1/bearers/9/traffic", json={"protocol": "tcp", "bps": 0})
    assert resp.status_code == 400
    state = client.get("/ues/1").json()
    assert state["bearers"]["9"]["active"] is False


def test_detach_stops_running_traffic(client):
    # BUG C: odłączenie UE powinno zatrzymać jego działający w tle ruch (brak osieroconych zadań)
    client.post("/ues", json={"ue_id": 1})
    client.post("/ues/1/bearers/9/traffic", json={"protocol": "tcp", "Mbps": 1})
    client.delete("/ues/1")
    assert traffic.traffic_manager.is_running(1, 9) is False


def test_out_of_range_bearer_id_in_path_is_validation_error(client):
    # BUG D: bearer_id spoza zakresu 1..9 w ścieżce powinien dać 422 (jak w body), a daje 400
    client.post("/ues", json={"ue_id": 1})
    resp = client.post("/ues/1/bearers/50/traffic", json={"protocol": "tcp", "Mbps": 1})
    assert resp.status_code == 422
