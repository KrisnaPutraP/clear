"""Joule front door (experiment): CLEAR as an A2A agent that SAP Joule calls.

Joule's agent-request action forwards the planner's message over A2A
(protocol 0.3.0) and gives the agent 60 seconds to answer. Agent runs often
take longer, so a new exception starts the agents in the background and the
planner asks for the status, approves, or rejects in later messages; each
answer waits up to WAIT_SECONDS for a run to end. No LLM reads the message:
commands are matched by IDs and keywords, and an approval must name the
validation it approves. The answer is text built from the case and its
records, so every number has the same source as in the UI.
"""

import asyncio
import base64
import hmac
import re
from dataclasses import dataclass

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, Part, TextPart
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError, UnsupportedOperationError
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse

from clear_app import view
from clear_app.contract import Clear
from clear_tools import read

APPROVER = "Planner via Joule"
WAIT_SECONDS = 40  # Joule waits 60 s for an answer; leave room for the network and the reply.
LOG_LINES = 4  # Latest timeline steps shown while a run is in progress.

_VALIDATION = re.compile(r"\bVAL-\d{4}\b", re.IGNORECASE)
_CASE = re.compile(r"\bCASE-\d{4}\b", re.IGNORECASE)
_SHIPMENT = re.compile(r"\bSHP-\d+\b", re.IGNORECASE)
_APPROVE = re.compile(r"\bapprove[ds]?\b", re.IGNORECASE)
_REJECT = re.compile(r"\breject(?:ed|s)?\b", re.IGNORECASE)
_REASON = re.compile(r"\b(?:because|reason:?|due to)\s+(.+)", re.IGNORECASE | re.DOTALL)
_STATUS = re.compile(r"\b(?:status|update|progress|plan|recommend\w*|happening|where are we)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Command:
    """What the planner asked for. kind: start, approve, reject, status, or help."""

    kind: str
    event_id: str | None = None
    validation_id: str | None = None
    case_id: str | None = None
    shipment_id: str | None = None
    reason: str | None = None


def interpret(text: str, event_ids: list[str]) -> Command:
    """Match a message to a command by IDs and keywords. Approvals and rejections come first."""
    validation = _match(_VALIDATION, text)
    case = _match(_CASE, text)
    shipment = _match(_SHIPMENT, text)
    if _APPROVE.search(text):
        return Command("approve", validation_id=validation)
    if _REJECT.search(text):
        reason = _REASON.search(text)
        return Command("reject", validation_id=validation, reason=reason.group(1).strip() if reason else None)
    event = next((e for e in event_ids if e.lower() in text.lower()), None)
    if event:
        return Command("start", event_id=event)
    if case or _STATUS.search(text):
        return Command("status", case_id=case, shipment_id=shipment)
    if shipment:
        return Command("start", shipment_id=shipment)
    return Command("help")


class CaseDesk:
    """Answers one planner message with the UI contract's operations."""

    def __init__(self, clear: Clear, approver: str = APPROVER, wait_seconds: float = WAIT_SECONDS):
        self.clear, self.approver, self.wait_seconds = clear, approver, wait_seconds

    def answer(self, text: str) -> str:
        with self.clear.snapshot():
            events = self.clear.list_events()
        command = interpret(text, [e["event_id"] for e in events])
        try:
            if command.kind == "start":
                return self._start(command, events)
            if command.kind in ("approve", "reject"):
                return self._decide(command)
            if command.kind == "status":
                case_id = command.case_id or self._latest_case(command.shipment_id)
                if case_id is None:
                    return self._help(events, f"There is no case for {command.shipment_id or 'any shipment'} yet.")
                return self.describe(case_id)
        except RuntimeError as error:  # An agent run is already in progress.
            return f"{error}\n\n{self.describe(self._latest_case())}"
        except LookupError as error:
            return self._help(events, str(error))
        return self._help(events)

    def describe(self, case_id: str) -> str:
        """The case as a short message: status, prediction, recommended option, and what is asked of the planner.

        Joule renders the answer as Markdown, so paragraphs are separated by blank lines.
        """
        with self.clear.snapshot():
            case = self.clear.get_case(case_id.upper())
            log = self.clear.get_case_log(case["case_id"])
        label, _ = view.STATUS[case["status"]]
        paragraphs = [f"**{case['case_id']} · {case['shipment_id']} · {label}**"]
        plan = case["plan"]
        if case["running"] and case["status"] in ("analyzing", "executing"):
            paragraphs.append("The agents are working. Latest steps:")
            paragraphs.append(_bullets(f"{e['actor']}: {e['summary']}" for e in log[-LOG_LINES:]))
            paragraphs.append("Ask me for the status again in a minute.")
            return "\n\n".join(paragraphs)
        if case["status_reason"] and not (plan and plan["escalation"] == case["status_reason"]):
            paragraphs.append(case["status_reason"])
        if not plan:
            return "\n\n".join(paragraphs)

        prediction = plan["impact"]["prediction"]
        rows = view.option_rows(plan)
        facts = [f"Exception: {plan['exception']}",
                 f"Predicted resolution: {prediction['predicted_days']:g} days ({view.prediction_note(prediction)})",
                 f"Current plan: {_coverage(rows[0])}"]
        recommended = next((r for r in rows if r["recommended"]), None)
        if recommended:
            facts.append(f"Recommended: {recommended['option']}: {_coverage(recommended)}; "
                         f"deferred orders: {recommended['deferred_orders']}")
        paragraphs.append(_bullets(facts))
        if plan["recommendation"]:
            paragraphs.append(plan["recommendation"])
        for action in plan["actions"]:
            validation = action["validation"]
            move = (f"{validation['quantity']:g} t from plant {validation['source_plant']} "
                    f"to plant {validation['destination_plant']}")
            if action["status"] == "awaiting_approval":
                paragraphs.append(f"Awaiting your approval: {action['validation_id']}, a stock transport order of "
                                  f"{move}, valid under the business rules. Reply **approve "
                                  f"{action['validation_id']}** or **reject {action['validation_id']} because "
                                  "<reason>**.")
            elif action["sto"]:
                approval = action["approval"]
                paragraphs.append(f"STO {action['sto']['purchase_order']} created: {move} ({action['validation_id']}, "
                                  f"{approval['approval_id']} by {approval['approver']}).")
        if plan["escalation"]:
            paragraphs.append(f"Escalation: {plan['escalation']}")
        if plan["next_check"]:
            paragraphs.append(f"Next check: {plan['next_check']}")
        return "\n\n".join(paragraphs)

    def _start(self, command: Command, events: list[dict]) -> str:
        event_id = command.event_id or self._next_event(command.shipment_id, events)
        case_id = self.clear.send_event(event_id)
        self.clear.wait(self.wait_seconds)
        return self.describe(case_id)

    def _decide(self, command: Command) -> str:
        pending = self._pending()
        if not command.validation_id:
            raise LookupError("Name the validation you decide on, for example: approve VAL-0002.")
        case_id = pending.get(command.validation_id)
        if case_id is None:
            raise LookupError(f"{command.validation_id} is not awaiting approval.")
        if command.kind == "reject" and not command.reason:
            return f"A rejection needs a reason: reject {command.validation_id} because <reason>."
        decision = "approved" if command.kind == "approve" else "rejected"
        self.clear.submit_decision(case_id, command.validation_id, self.approver, decision, command.reason)
        self.clear.wait(self.wait_seconds)
        return self.describe(case_id)

    def _pending(self) -> dict[str, str]:
        """Validations awaiting approval, with their case."""
        pending = {}
        with self.clear.snapshot():
            for case in self.clear.list_cases():
                if case["status"] == "awaiting_approval":
                    plan = self.clear.get_case(case["case_id"])["plan"] or {"actions": []}
                    pending |= {a["validation_id"]: case["case_id"] for a in plan["actions"]
                                if a["status"] == "awaiting_approval"}
        return pending

    def _next_event(self, shipment_id: str, events: list[dict]) -> str:
        """The shipment's first prepared event that has not happened yet."""
        with self.clear.snapshot():
            recorded = {e["event_id"] for e in read.get_shipment(self.clear.store, shipment_id.upper())["events"]}
        for event in events:
            if event["shipment_id"] == shipment_id.upper() and event["event_id"] not in recorded:
                return event["event_id"]
        raise LookupError(f"No new event for {shipment_id.upper()}.")

    def _latest_case(self, shipment_id: str | None = None) -> str | None:
        with self.clear.snapshot():
            cases = self.clear.list_cases()
        return next((c["case_id"] for c in cases if shipment_id is None or c["shipment_id"] == shipment_id.upper()),
                    None)

    def _help(self, events: list[dict], note: str | None = None) -> str:
        paragraphs = [note] if note else []
        paragraphs.append("I am CLEAR. I resolve exceptions on inbound shipments. You can:")
        paragraphs.append(_bullets([
            "start an event from the logistics feed, for example: work S1-DOC-HOLD",
            "ask for the status of a case or shipment, for example: status of SHP-1001",
            "approve or reject a validated transfer: approve VAL-0002, or reject VAL-0002 because <reason>",
        ]))
        paragraphs.append("Events in the feed:")
        paragraphs.append(_bullets(f"{e['event_id']} ({e['shipment_id']}): {e['description']}" for e in events))
        latest = self._latest_case()
        if latest:
            paragraphs.append(f"Latest case: {self.describe(latest).splitlines()[0]}")
        return "\n\n".join(paragraphs)


class ClearExecutor(AgentExecutor):
    """One A2A task per message: CaseDesk answers, and the task completes with the answer."""

    def __init__(self, desk: CaseDesk):
        self.desk = desk

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task(context.message)
        if not context.current_task:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        reply = await asyncio.to_thread(self.desk.answer, context.get_user_input())
        await updater.add_artifact([Part(root=TextPart(text=reply))], name="clear_answer")
        await updater.complete(new_agent_text_message(reply, task.context_id, task.id))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())


def agent_card(url: str) -> AgentCard:
    return AgentCard(
        name="CLEAR",
        description=("Cross-border supply chain exception resolution: turns a shipment exception into a validated "
                     "recovery plan, reports the case status, and takes a planner's approval or rejection of a "
                     "validated stock transport order."),
        url=url,
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        skills=[
            AgentSkill(id="work-exception", name="Work a shipment exception",
                       description="Starts the agents on an event from the logistics feed.",
                       tags=["shipment exception", "customs hold", "port congestion"],
                       examples=["Work S1-DOC-HOLD", "SHP-1002 is delayed by yard congestion"]),
            AgentSkill(id="case-status", name="Case status",
                       description="The case status, the predicted resolution time, and the recommended option.",
                       tags=["status", "recovery plan"], examples=["Status of SHP-1001"]),
            AgentSkill(id="decide-transfer", name="Approve or reject a transfer",
                       description="Records the planner's decision on a validated stock transport order.",
                       tags=["approval", "stock transport order"],
                       examples=["approve VAL-0002", "reject VAL-0002 because plant 1200 needs the stock"]),
        ],
    )


class BasicAuth:
    """Every request needs the Basic credentials of the BTP destination that Joule calls through."""

    def __init__(self, app, user: str, password: str):
        self.app = app
        self.expected = b"Basic " + base64.b64encode(f"{user}:{password}".encode())

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            header = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(header, self.expected):
                response = PlainTextResponse("Unauthorized", status_code=401,
                                             headers={"WWW-Authenticate": 'Basic realm="CLEAR"'})
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def build_app(clear: Clear, url: str, user: str | None = None, password: str | None = None,
              wait_seconds: float = WAIT_SECONDS) -> Starlette:
    """The A2A server: the agent card at /.well-known/agent-card.json and JSON-RPC at /."""
    handler = DefaultRequestHandler(agent_executor=ClearExecutor(CaseDesk(clear, wait_seconds=wait_seconds)),
                                    task_store=InMemoryTaskStore())
    app = A2AStarletteApplication(agent_card=agent_card(url), http_handler=handler).build()
    if password:
        app.add_middleware(BasicAuth, user=user or "clear", password=password)
    return app


def _coverage(row: dict) -> str:
    return f"covers {row['coverage_days']:g} of {row['needed_days']:g} days needed, {row['label']}"


def _bullets(items) -> str:
    return "\n".join(f"- {item}" for item in items)


def _match(pattern: re.Pattern, text: str) -> str | None:
    found = pattern.search(text)
    return found.group(0).upper() if found else None
