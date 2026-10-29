"""The Joule front door: message routing, and S1 over A2A JSON-RPC with the scripted model."""

import base64
import re
import threading
import uuid

import pytest

pytest.importorskip("a2a")

from starlette.testclient import TestClient  # noqa: E402

from clear_agents.testing import ScriptedDirector  # noqa: E402
from clear_app.contract import Clear  # noqa: E402
from clear_app.joule import CaseDesk, Command, build_app, interpret  # noqa: E402

EVENTS = ["S1-DOC-HOLD", "S1-ETA-SLIP", "S2-CONGESTION"]


@pytest.mark.parametrize("text, command", [
    ("approve VAL-0002", Command("approve", validation_id="VAL-0002")),
    ("Approved val-0002, go ahead", Command("approve", validation_id="VAL-0002")),
    ("Should I approve it?", Command("approve")),
    ("reject VAL-0002 because plant 1200 needs the stock",
     Command("reject", validation_id="VAL-0002", reason="plant 1200 needs the stock")),
    ("reject VAL-0002", Command("reject", validation_id="VAL-0002")),
    ("Work S1-DOC-HOLD please", Command("start", event_id="S1-DOC-HOLD")),
    ("What is the status of SHP-1001?", Command("status", shipment_id="SHP-1001")),
    ("show CASE-0001", Command("status", case_id="CASE-0001")),
    ("SHP-1002 is stuck at the port", Command("start", shipment_id="SHP-1002")),
    ("hello", Command("help")),
])
def test_interpret(text, command):
    assert interpret(text, EVENTS) == command


@pytest.fixture
def clear(store, monkeypatch):
    monkeypatch.setenv("CLEAR_PREDICTION_BACKEND", "baseline")
    return Clear(store, ScriptedDirector(store))


def send(client: TestClient, text: str, auth: str | None = None) -> str:
    """One Joule turn: message/send as Joule's agent-request sends it, and the answer text."""
    response = client.post("/", headers={"Authorization": auth} if auth else {}, json={
        "jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "message/send",
        "params": {"message": {"role": "user", "kind": "message", "messageId": str(uuid.uuid4()),
                               "parts": [{"kind": "text", "text": text}]}},
    })
    response.raise_for_status()
    task = response.json()["result"]
    assert task["status"]["state"] == "completed"
    # The Joule function shows the final status message; the same text is the task's artifact.
    assert task["artifacts"][0]["parts"][0]["text"] == task["status"]["message"]["parts"][0]["text"]
    return task["status"]["message"]["parts"][0]["text"]


def test_s1_through_joule(clear):
    client = TestClient(build_app(clear, "http://testserver/", wait_seconds=30))

    answer = send(client, "SHP-1001 was flagged by customs")
    assert "CASE-0001 · SHP-1001 · Awaiting approval" in answer
    assert "Predicted resolution: 3 days" in answer
    validation_id = re.search(r"approve (VAL-\d{4})", answer).group(1)

    assert "Name the validation" in send(client, "approve it")
    assert "needs a reason" in send(client, f"reject {validation_id}")
    assert "not awaiting approval" in send(client, "approve VAL-0999")

    answer = send(client, f"approve {validation_id}")
    assert "Monitoring" in answer
    assert f"STO 4500001023 created: 20 t from plant 1200 to plant 1100 ({validation_id}, APR-0001 by " \
           "Planner via Joule)" in answer

    assert "S1-ETA-SLIP" in send(client, "hello")
    assert "CASE-0001 · SHP-1001 · Monitoring" in send(client, "status of SHP-1001")


class SlowAgents:
    """Agents still working when Joule's time is up; the run ends when the test says so."""

    def __init__(self):
        self.release = threading.Event()

    def work_event(self, case_id, event):
        self.release.wait(10)
        return {}

    def work_approval(self, case_id, approval):
        return {}


def test_a_long_run_answers_in_time_and_keeps_going(store):
    agents = SlowAgents()
    clear = Clear(store, agents=agents)
    desk = CaseDesk(clear, wait_seconds=0.1)

    answer = desk.answer("work S2-CONGESTION")
    assert "CASE-0001 · SHP-1002 · Analyzing" in answer
    assert "The agents are working" in answer and "Event feed:" in answer
    assert "An agent run is in progress" in desk.answer("work S1-DOC-HOLD")
    assert clear.running

    agents.release.set()
    clear.wait(5)
    assert not clear.running


def test_agent_card_and_basic_auth(clear):
    client = TestClient(build_app(clear, "https://clear.example/", user="joule", password="secret"))
    assert client.get("/.well-known/agent-card.json").status_code == 401

    auth = "Basic " + base64.b64encode(b"joule:secret").decode()
    card = client.get("/.well-known/agent-card.json", headers={"Authorization": auth}).json()
    assert card["url"] == "https://clear.example/"
    assert card["protocolVersion"] == "0.3.0"
    assert "Events in the feed" in send(client, "hi", auth)
