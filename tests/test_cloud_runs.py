"""CLEAR as deployed (docs/PLAN.md §2c, §5b, §7b), end to end with stand-ins for AWS: the UI
records events and decisions in DynamoDB and invokes the runtime; the runtime's agents call
their tools through the gateway; the Lambda function runs them on the same table."""

import json

import pytest

from aws_fakes import RUNTIME_ARN, FakeDeployment
from clear_agents import caselog, runner
from clear_aws import runtime
from clear_aws.remote import CLIENT_CONFIG, RuntimeAgents
from clear_tools.events import prepared_event

WRITE_TOOLS = {"validate_action", "create_stock_transport_order"}


@pytest.fixture
def deployment(monkeypatch):
    return FakeDeployment(monkeypatch)


def test_s1_runs_on_the_deployment_like_it_runs_locally(deployment):
    clear = deployment.clear()
    case_id = clear.send_event("S1-DOC-HOLD", wait=True)
    with clear.snapshot():
        case, log = clear.get_case(case_id), clear.get_case_log(case_id)

    assert case["status"] == "awaiting_approval"
    assert [e["tool"] for e in log if e.get("flag") == "rejected"] == ["validate_action"]
    assert [e["tool"] for e in log if e.get("flag") == "discrepancy"] == ["reconcile_documents"]
    [action] = case["plan"]["actions"]
    assert action["validation"]["quantity"] == 100

    clear.submit_decision(case_id, action["validation_id"], "Demo Planner", "approved", wait=True)
    with clear.snapshot():
        case = clear.get_case(case_id)

    assert case["status"] == "monitoring"
    assert case["plan"]["actions"][0]["sto"]["purchase_order"] == "4500001023"


def test_only_the_action_role_sends_validation_and_writes(deployment):
    clear = deployment.clear()
    case_id = clear.send_event("S1-DOC-HOLD", wait=True)
    [action] = clear.get_case(case_id)["plan"]["actions"]
    clear.submit_decision(case_id, action["validation_id"], "Demo Planner", "approved", wait=True)

    by_role = {"agents": set(), "action": set()}
    for client in deployment.gateway_clients:
        by_role["action" if client.credentials else "agents"].update(client.calls)
        assert client.started
        assert client.stopped
    assert WRITE_TOOLS <= by_role["action"] <= WRITE_TOOLS | {"get_inventory"}
    assert not WRITE_TOOLS & by_role["agents"]


def test_one_runtime_session_per_case_without_retries(deployment):
    clear = deployment.clear()
    clear.send_event("S1-DOC-HOLD", wait=True)
    clear.send_event("S2-CONGESTION", wait=True)

    first, second = deployment.runtime_client.invocations
    assert json.loads(first["payload"]) == {"run": "event", "case_id": "CASE-0001", "event_id": "S1-DOC-HOLD"}
    assert first["agentRuntimeArn"] == RUNTIME_ARN
    assert first["runtimeSessionId"] != second["runtimeSessionId"]
    assert first["runtimeSessionId"].endswith("-CASE-0001")
    assert len(first["runtimeSessionId"]) >= 33  # The API's minimum.
    assert CLIENT_CONFIG.retries["max_attempts"] == 1
    assert CLIENT_CONFIG.read_timeout > 15 * 60


def test_unreachable_runtime_leaves_a_readable_case(deployment):
    class Unreachable:
        def invoke_agent_runtime(self, **params):
            raise ConnectionError("Could not connect to the endpoint URL")

    store = deployment.ui_store
    clear = deployment.clear()
    clear.agents = RuntimeAgents(store, RUNTIME_ARN, client=Unreachable())

    case = clear.get_case(clear.send_event("S2-CONGESTION", wait=True))

    assert case["status"] == "needs_human_decision"
    assert "Could not connect" in case["status_reason"]


def test_unreachable_gateway_fails_the_run_not_the_runtime(deployment):
    store = deployment.ui_store
    case_id = runner.open_case_for_event(store, prepared_event(store, "S2-CONGESTION"))

    class Down:
        def __enter__(self):
            raise ConnectionError("gateway unreachable")

        def __exit__(self, *exc_info):
            return False

    result = runtime.handle({"run": "event", "case_id": case_id, "event_id": "S2-CONGESTION"},
                            store=deployment.runtime_store, gateway=Down())

    assert result["status"] == "needs_human_decision"
    assert "gateway unreachable" in caselog.get_case(store, case_id)["status_reason"]


@pytest.mark.parametrize("payload, error", [
    ({"run": "deploy"}, ValueError),
    ({"run": "event", "case_id": "CASE-0001"}, ValueError),
    ({"run": "approval", "case_id": "CASE-0001", "approval_id": ""}, ValueError),
    ({"run": "event", "case_id": "CASE-0042", "event_id": "S1-DOC-HOLD"}, LookupError),
])
def test_the_runtime_rejects_payloads_it_cannot_work(deployment, payload, error):
    with pytest.raises(error):
        runtime.handle(payload, store=deployment.runtime_store, gateway=deployment.gateway())
