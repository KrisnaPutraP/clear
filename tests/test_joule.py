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
from clear_app.joule import CaseDesk, Command, _follow_up, build_app, interpret  # noqa: E402
from clear_app.joule_intent import Intent  # noqa: E402

EVENTS = ["S1-DOC-HOLD", "S1-ETA-SLIP", "S2-CONGESTION"]


@pytest.mark.parametrize("text, command", [
    ("approve VAL-0002", Command("approve", validation_id="VAL-0002")),
    ("approve val-0002.", Command("approve", validation_id="VAL-0002")),
    ("Approved val-0002, go ahead", Command("decisions")),
    ("Should I approve it?", Command("decisions")),
    ("Do not approve VAL-0002", Command("hold", validation_id="VAL-0002")),
    ("should I approve VAL-0002?", Command("decisions")),
    ("why was VAL-0002 approved?", Command("decisions")),
    ("don't reject VAL-0002, approve later", Command("hold", validation_id="VAL-0002")),
    ("Cancel, keep VAL-0002 waiting", Command("hold", validation_id="VAL-0002")),
    ("what needs my decision?", Command("decisions")),
    ("anything pending?", Command("decisions")),
    ("reject VAL-0002 because plant 1200 needs the stock",
     Command("reject", validation_id="VAL-0002", reason="plant 1200 needs the stock")),
    ("reject VAL-0002", Command("reject", validation_id="VAL-0002")),
    ("Work S1-DOC-HOLD please", Command("start", event_id="S1-DOC-HOLD")),
    ("What is the status of SHP-1001?", Command("status", shipment_id="SHP-1001")),
    ("show CASE-0001", Command("status", case_id="CASE-0001")),
    ("details CASE-0001", Command("details", case_id="CASE-0001")),
    ("Show the detailed plan for SHP-1001", Command("details", shipment_id="SHP-1001")),
    ("SHP-1002 is stuck at the port", Command("start", shipment_id="SHP-1002")),
    ("hello", Command("help")),
    ("list cases", Command("list")),
    ("Please show open cases", Command("list")),
    ("SHOW THE ALL CASES", Command("list")),
    ("approve VAL-0002 and show open cases", Command("decisions")),
])
def test_interpret(text, command):
    assert interpret(text, EVENTS) == command


@pytest.fixture
def clear(store, monkeypatch):
    monkeypatch.setenv("CLEAR_PREDICTION_BACKEND", "baseline")
    return Clear(store, ScriptedDirector(store))


def send(client: TestClient, text: str, auth: str | None = None) -> str:
    """One Joule turn: message/send as Joule's agent-request sends it, and the answer text."""
    return send_task(client, text, auth)["status"]["message"]["parts"][0]["text"]


def send_task(client: TestClient, text: str, auth: str | None = None) -> dict:
    """One Joule turn, and the whole A2A task Joule receives."""
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
    return task


def test_s1_through_joule(clear):
    client = TestClient(build_app(clear, "http://testserver/", wait_seconds=30))

    answer = send(client, "SHP-1001 was flagged by customs")
    assert "CASE-0001 · SHP-1001 · Awaiting approval" in answer
    assert "Predicted resolution: **3 days**" in answer
    assert "**Supply impact**" in answer
    assert "**Approval required**" in answer
    assert "details CASE-0001" in answer
    validation_id = re.search(r"approve (VAL-\d{4})", answer).group(1)

    # Nothing below changes the case until a confirmation code comes back.
    reply = send(client, "approve it")
    assert f"approve {validation_id}" in reply and "nothing changes until you do" in reply
    assert "nothing changed" in send(client, f"do not approve {validation_id}").lower()
    assert "Decisions waiting for you" in send(client, f"should I approve {validation_id}?")
    assert "Why do you reject" in send(client, f"reject {validation_id}")
    assert "not awaiting approval" in send(client, "approve VAL-0999")
    preview = send(client, f"approve {validation_id}")
    assert "Nothing has changed yet" in preview
    stale = re.search(r"code ([A-Z0-9]{4})", preview).group(1)
    assert "nothing changed" in send(client, f"Cancel, keep {validation_id} waiting").lower()
    send(client, f"Confirm approval of {validation_id}, code {stale}")
    assert clear.get_case("CASE-0001")["status"] == "awaiting_approval"

    task = send_task(client, f"approve {validation_id}")
    buttons = task["artifacts"][1]["parts"][0]["data"]
    assert buttons["primary"]["title"] == "Confirm approval"
    assert buttons["secondary"]["value"] == f"Cancel, keep {validation_id} waiting"
    answer = send(client, buttons["primary"]["value"])
    assert "Monitoring" in answer
    assert f"STO 4500001023 created: 20 t from plant 1200 to plant 1100 ({validation_id}, APR-0001 by " \
           "Planner via Joule)" in answer

    assert "S1-ETA-SLIP" in send(client, "hello")
    assert "CASE-0001 · SHP-1001 · Monitoring" in send(client, "status of SHP-1001")


def test_case_list_is_read_only_and_puts_approval_before_monitoring(clear):
    client = TestClient(build_app(clear, "http://testserver/", wait_seconds=30))
    assert "No cases have been created" in send(client, "show open cases")
    assert clear.list_cases() == []
    send(client, "work S1-DOC-HOLD")
    send(client, "work S2-CONGESTION")
    before = [clear.get_case(c["case_id"]) for c in clear.list_cases()]
    answer = send(client, "list cases")
    assert answer.index("CASE-0001") < answer.index("CASE-0002")
    assert "Awaiting approval" in answer and "Monitoring" in answer
    assert "Exception:" in answer and "status CASE-0001" in answer
    assert [clear.get_case(c["case_id"]) for c in clear.list_cases()] == before


def test_shipment_status_before_a_case_is_read_only(clear):
    client = TestClient(build_app(clear, "http://testserver/", wait_seconds=30))
    shipment_before = clear.store.read("logistics/shipments")
    for command in ("status of SHP-1001", "details of SHP-1001"):
        answer = send(client, command)
        assert "SHP-1001 · Shipment status" in answer
        assert "in_transit" in answer and "4500001021" in answer
        assert "Tanjung Priok" in answer and "2026-10-31T14:00:00+07:00" in answer
        assert "Recorded exception: None" in answer
        assert "EV-1001-01" in answer
        assert "Prepared demo events" in answer and "have not been submitted" in answer
        assert "work S1-DOC-HOLD" in answer
        assert "S2-CONGESTION" not in answer
    assert clear.list_cases() == []
    assert clear.store.read("logistics/shipments") == shipment_before
    assert not clear.running
    assert "Unknown shipment_id: SHP-9999" in send(client, "status of SHP-9999")
    assert "Unknown" in send(client, "status CASE-9999")
    assert clear.list_cases() == []


def test_pre_case_status_preserves_a_recorded_exception(clear):
    shipments = clear.store.read("logistics/shipments")
    shipments[0]["exception"] = {"type": "customs_document_hold", "description": "Awaiting corrected invoice."}
    clear.store.write("logistics/shipments", shipments)
    answer = CaseDesk(clear).answer("status of SHP-1001")
    assert "Recorded exception: Awaiting corrected invoice." in answer
    assert "Analysis has not started" in answer
    assert clear.list_cases() == []


def test_escalation_summary_keeps_the_decision_and_all_follow_up(clear):
    desk = CaseDesk(clear, wait_seconds=30)
    desk.answer("work S1-DOC-HOLD")
    action = clear.get_case("CASE-0001")["plan"]["actions"][0]
    desk.answer(f"approve {action['validation_id']}")
    desk.answer("work S1-ETA-SLIP")
    case = clear.get_case("CASE-0001")
    assert case["status"] == "needs_human_decision"
    summary = desk.answer("status of SHP-1001")
    assert "**Decision required**" in summary
    assert case["plan"]["escalation"] in summary
    assert _follow_up(case["plan"]["next_check"]) in summary
    assert "**Evidence and rationale**" not in summary
    details = desk.answer("details CASE-0001")
    assert "**Evidence and rationale**" in details
    assert "**Assessed options**" in details
    assert case["plan"]["exception"] in details
    assert case["plan"]["recommendation"] in details
    assert clear.get_case("CASE-0001")["plan"] == case["plan"]


def test_numbered_follow_up_preserves_quantities_and_decimal_days():
    text = "1) Monitor the 3.8-day window. 2) Confirm 20 MT in transit. 3) Track plant 1200 at 40 MT."
    assert _follow_up(text) == (
        "1. Monitor the 3.8-day window.\n\n"
        "2. Confirm 20 MT in transit.\n\n"
        "3. Track plant 1200 at 40 MT."
    )
    assert _follow_up("Monitor 3.8 days and 20 MT.") == "Monitor 3.8 days and 20 MT."


def test_rejected_transfer_does_not_offer_an_active_approval_command(clear):
    desk = CaseDesk(clear, wait_seconds=30)
    desk.answer("work S1-DOC-HOLD")
    action = clear.get_case("CASE-0001")["plan"]["actions"][0]
    preview = desk.respond(f"reject {action['validation_id']} because the planner needs another route")
    assert "Reason: the planner needs another route" in preview.text
    reply = desk.answer(preview.buttons[0].value)
    assert "Needs a human decision" in reply
    assert "not currently accepting approval" in reply
    assert "**Approval required**" not in reply
    assert "To approve:" not in reply
    decisions = desk.answer("what needs my decision?")
    assert "Needs a human decision" in decisions and "To approve:" not in decisions


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


class FakeModel:
    """Stands in for Claude: a fixed intent per message, and the context it was given."""

    def __init__(self, intents: dict[str, Intent | None]):
        self.intents, self.contexts = intents, []

    def __call__(self, text, context):
        self.contexts.append(context)
        return self.intents.get(text)


def test_the_model_reads_free_text_and_a_write_still_needs_the_code(clear):
    desk = CaseDesk(clear, wait_seconds=30)
    desk.answer("work S1-DOC-HOLD")
    validation_id = clear.get_case("CASE-0001")["plan"]["actions"][0]["validation_id"]
    model = FakeModel({
        "jangan approve dulu, tunggu bea cukai": Intent(kind="hold"),
        "oke approve transfernya": Intent(kind="approve"),
        "kenapa nggak transfer semua?": Intent(kind="question"),
        "status of the mill shipment": Intent(kind="status", shipment_id="SHP-9999"),
    })
    desk.understand = model

    assert "nothing changed" in desk.answer("jangan approve dulu, tunggu bea cukai").lower()
    assert model.contexts[0]["transfers_awaiting_approval"][0]["validation_id"] == validation_id
    assert "Assessed options" in desk.answer("kenapa nggak transfer semua?")
    assert "There is no case" not in desk.answer("status of the mill shipment")  # Unknown IDs are dropped.

    preview = desk.respond("oke approve transfernya")  # The only transfer waiting; no ID needed.
    assert f"Confirm approval · {validation_id}" in preview.text
    assert clear.get_case("CASE-0001")["status"] == "awaiting_approval"

    # A confirmation that the model reads as "hold" does not execute.
    model.intents[f"no, do not {preview.buttons[0].value}"] = Intent(kind="hold")
    assert "nothing changed" in desk.answer(f"no, do not {preview.buttons[0].value}").lower()
    assert clear.get_case("CASE-0001")["status"] == "awaiting_approval"

    preview = desk.respond("oke approve transfernya")
    assert "Monitoring" in desk.answer(preview.buttons[0].value)  # The model has no reading: rules, code wins.


def test_without_the_model_the_rules_answer(clear):
    desk = CaseDesk(clear, wait_seconds=30, understand=FakeModel({"approve VAL-0009": Intent(kind="help")}))
    assert "Events in the feed" in desk.answer("hi")  # The model returns nothing.
    assert "`VAL-0009` is not awaiting approval" in desk.answer("approve VAL-0009")  # Unsure: the rules decide.
