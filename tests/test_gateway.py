"""The agents' tools through AgentCore Gateway (docs/PLAN.md §2a, §5b, §6a): same tools, the call
travels, errors come back as the tool raised them, and the Action agent signs with its own role."""

import json

import pytest

from aws_fakes import FakeGatewayClient
from clear_aws import gateway, settings
from clear_aws.gateway import Gateway, GatewayError, unpack


class Recorder:
    """Connections made by a Gateway, without a network."""

    def __init__(self, monkeypatch):
        self.clients: list[FakeGatewayClient] = []
        monkeypatch.setattr(gateway, "role_credentials", lambda role, session: f"credentials of {role}")

    def __call__(self, credentials):
        client = FakeGatewayClient(credentials)
        self.clients.append(client)
        return client


def test_the_action_agent_calls_with_its_own_role(monkeypatch):
    connect = Recorder(monkeypatch)
    with Gateway("https://gateway.example", settings.ACTION_ROLE, connect) as invoke_for:
        assert invoke_for("evidence") is not None
    agents, action = connect.clients

    assert agents.credentials is None  # The runtime's own role.
    assert action.credentials == f"credentials of {settings.ACTION_ROLE}"
    assert all(client.started and client.stopped for client in connect.clients)


def test_outside_the_runtime_the_other_agents_call_with_the_agents_role(monkeypatch):
    connect = Recorder(monkeypatch)
    with Gateway("https://gateway.example", settings.ACTION_ROLE, connect, agents_role=settings.AGENTS_ROLE):
        pass
    agents, action = connect.clients

    assert agents.credentials == f"credentials of {settings.AGENTS_ROLE}"
    assert action.credentials == f"credentials of {settings.ACTION_ROLE}"


def test_without_an_action_role_all_agents_share_one_session(monkeypatch):
    connect = Recorder(monkeypatch)
    with Gateway("https://gateway.example", None, connect):
        pass

    [client] = connect.clients
    assert client.stopped


def test_a_failed_connection_closes_what_was_opened(monkeypatch):
    connect = Recorder(monkeypatch)

    def fail(role, session):
        raise PermissionError("not authorized to perform sts:AssumeRole")

    monkeypatch.setattr(gateway, "role_credentials", fail)

    with pytest.raises(PermissionError):
        with Gateway("https://gateway.example", settings.ACTION_ROLE, connect):
            pass
    [agents] = connect.clients
    assert agents.stopped


def test_null_arguments_are_left_out(monkeypatch):
    sent = []

    class Client(FakeGatewayClient):
        def call_tool_sync(self, tool_use_id, name, arguments, read_timeout_seconds=None):
            sent.append((name, arguments))
            return {"status": "success", "content": [{"text": json.dumps({"ok": True})}]}

    with Gateway("https://gateway.example", None, Client) as invoke_for:
        invoke_for("impact")("calculate_supply_risk", {"shipment_id": "SHP-1001", "source_plant": None})

    assert sent == [(f"{settings.TARGET}___calculate_supply_risk", {"shipment_id": "SHP-1001"})]


def test_tool_errors_are_raised_as_the_tool_raised_them():
    with pytest.raises(PermissionError, match="APR-0001 rejected VAL-0001."):
        unpack("create_stock_transport_order",
               json.dumps({"error": {"type": "PermissionError", "message": "APR-0001 rejected VAL-0001."}}))

    with pytest.raises(RuntimeError) as raised:
        unpack("get_shipment", json.dumps({"error": {"type": "ConcurrentWriteError", "message": "busy"}}))
    # Strands then words it "Error: ConcurrentWriteError - busy", as in a local run.
    assert type(raised.value).__name__ == "ConcurrentWriteError"


def test_gateway_failures_and_odd_responses_are_gateway_errors():
    with pytest.raises(GatewayError, match="Unexpected response"):
        unpack("get_shipment", "An internal error occurred. Please retry later.")

    class Refusing(FakeGatewayClient):
        def call_tool_sync(self, tool_use_id, name, arguments, read_timeout_seconds=None):
            return {"status": "error", "content": [{"text": "Tool call not allowed by policy"}]}

    with Gateway("https://gateway.example", None, Refusing) as invoke_for:
        with pytest.raises(GatewayError, match="not allowed by policy"):
            invoke_for("action")("create_stock_transport_order", {"validation_id": "VAL-1", "approval_id": "APR-1"})


def test_the_runtime_needs_the_gateway_url_the_cli_sets(monkeypatch):
    monkeypatch.delenv(settings.GATEWAY_URL_SETTING, raising=False)
    with pytest.raises(LookupError, match=settings.GATEWAY_URL_SETTING):
        Gateway.from_env()

    monkeypatch.setenv(settings.GATEWAY_URL_SETTING, "https://gateway.example")
    monkeypatch.setenv(settings.ACTION_ROLE_SETTING, settings.ACTION_ROLE)
    monkeypatch.setenv(settings.AGENTS_ROLE_SETTING, settings.AGENTS_ROLE)
    found = Gateway.from_env()
    assert (found.url, found.action_role, found.agents_role) == ("https://gateway.example", settings.ACTION_ROLE,
                                                                 settings.AGENTS_ROLE)
