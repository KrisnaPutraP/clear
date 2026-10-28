"""HTTP workflows use the real contract, deterministic tools, and scripted agents."""

import threading

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from clear_agents import caselog
from clear_agents.testing import ScriptedDirector
from clear_app.api import create_app
from clear_app.bootstrap import create_clear
from clear_app.contract import Clear
from clear_tools.sto import EXECUTED


@pytest.fixture
def service(store):
    clear = Clear(store, ScriptedDirector(store))
    yield clear
    clear.wait(30)


def send(client, service, event):
    response = client.post(f"/events/{event}")
    assert response.status_code == 202, response.text
    service.wait(30)
    assert not service.running
    case_id = response.json()["case_id"]
    return case_id, client.get(f"/cases/{case_id}").json()


def test_http_s1_approval_execution_and_eta_reassessment(service, store):
    with TestClient(create_app(service)) as client:
        assert client.get("/health").json()["mode"] == "scripted"
        assert len(client.get("/events").json()) == 3
        case_id, case = send(client, service, "S1-DOC-HOLD")
        assert case["status"] == "awaiting_approval"
        assert case["reconciliation"]["discrepancies"]
        assert not store.read(EXECUTED)
        before = client.get(f"/cases/{case_id}/log").json()
        assert any(entry.get("flag") == "rejected" for entry in before)
        assert client.get(f"/cases/{case_id}/log?after_seq={before[-1]['seq']}").json() == []

        payload = {"validation_id": case["plan"]["actions"][0]["validation_id"],
                   "approver": "Demo Planner", "decision": "approved"}
        response = client.post(f"/cases/{case_id}/decisions", json=payload)
        assert response.status_code == 202, response.text
        service.wait(30)
        assert not service.running
        after = client.get(f"/cases/{case_id}").json()
        assert after["status"] == "monitoring"
        assert after["plan"]["actions"][0]["status"] == "executed"
        assert len(store.read(EXECUTED)) == 1
        delta = client.get(f"/cases/{case_id}/log?after_seq={before[-1]['seq']}").json()
        assert delta and all(entry["seq"] > before[-1]["seq"] for entry in delta)
        assert client.post(f"/cases/{case_id}/decisions", json=payload).status_code == 409

        same_case_id, updated = send(client, service, "S1-ETA-SLIP")
        assert same_case_id == case_id
        assert updated["status"] == "needs_human_decision"
        assert len(store.read(EXECUTED)) == 1


def test_http_s2_keeps_plan_without_writing(service, store):
    with TestClient(create_app(service)) as client:
        _, case = send(client, service, "S2-CONGESTION")
        assert case["status"] == "monitoring"
        assert case["plan"]["impact"]["covered"]
        assert not case["plan"]["actions"]
        assert not store.read(EXECUTED)


def test_http_decision_validation_and_case_binding(service, store):
    with TestClient(create_app(service)) as client:
        case_id, case = send(client, service, "S1-DOC-HOLD")
        action = case["plan"]["actions"][0]
        payload = {"validation_id": action["validation_id"], "approver": "Planner", "decision": "rejected"}
        for reason in (None, "   "):
            assert client.post(f"/cases/{case_id}/decisions", json={**payload, "reason": reason}).status_code == 422
        assert client.post(f"/cases/{case_id}/decisions", json={**payload, "approver": " ", "reason": "No"}).status_code == 422
        assert client.post(f"/cases/{case_id}/decisions", json={**payload, "validation_id": "VAL-other", "reason": "No"}).status_code == 409
        other_case, _ = send(client, service, "S2-CONGESTION")
        assert client.post(f"/cases/{other_case}/decisions", json={**payload, "reason": "No"}).status_code == 409
        assert not store.read("records/approvals")
        assert client.post(f"/cases/{case_id}/decisions", json={**payload, "reason": "Use another plan"}).status_code == 202
        assert client.get(f"/cases/{case_id}").json()["status"] == "needs_human_decision"
        assert not store.read(EXECUTED)


def test_http_unknown_ids_and_cursor_errors(service):
    with TestClient(create_app(service)) as client:
        for path in ("/cases/unknown", "/cases/unknown/log"):
            assert client.get(path).status_code == 404
        assert client.post("/events/unknown").status_code == 404
        assert client.get("/cases/unknown/log?after_seq=-1").status_code == 422
        assert not service.running


def test_http_conflicting_events_do_not_start_a_second_writer(store):
    entered, release = threading.Event(), threading.Event()

    class BlockingAgents:
        def work_event(self, case_id, event):
            entered.set()
            release.wait(10)
            return caselog.update_case(store, case_id, status="monitoring")

        def work_approval(self, case_id, approval):
            raise AssertionError("No approval was expected")

    service = Clear(store, agents=BlockingAgents())
    with TestClient(create_app(service)) as client:
        try:
            assert client.post("/events/S2-CONGESTION").status_code == 202
            assert entered.wait(5)
            assert client.get("/health").json()["running"]
            assert client.post("/events/S1-DOC-HOLD").status_code == 409
            assert len(client.get("/cases").json()) == 1
        finally:
            release.set()
            service.wait(10)


def test_scripted_bootstrap_ignores_cloud_configuration(tmp_path, monkeypatch):
    # Keep the developer's local configuration out of this offline bootstrap test.
    monkeypatch.setattr("clear_app.bootstrap.settings.load_env", lambda: None)
    monkeypatch.setenv("CLEAR_UI_SCRIPTED", "1")
    monkeypatch.setenv("CLEAR_RUNTIME_DIR", str(tmp_path / "demo"))
    monkeypatch.setenv("CLEAR_AGENT_RUNTIME_ARN", "do-not-use")
    monkeypatch.setenv("AGENTCORE_GATEWAY_TOOLS_URL", "do-not-use")
    monkeypatch.setenv("CLEAR_PREDICTION_BACKEND", "auto")
    clear = create_clear()
    with TestClient(create_app(clear)) as client:
        info = client.get("/health").json()
        assert info["mode"] == "scripted"
        assert info["prediction"] == "Baseline median"
        assert len(client.get("/events").json()) == 3
