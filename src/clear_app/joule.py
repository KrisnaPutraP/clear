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

from clear_agents.plan import format_points
from clear_app import view
from clear_app.contract import Clear
from clear_tools import read

APPROVER = "Planner via Joule"
WAIT_SECONDS = 40  # Joule waits 60 s for an answer; leave room for the network and the reply.
LOG_LINES = 4  # Latest timeline steps shown while a run is in progress.

_VALIDATION = re.compile(r"\bVAL-\d{4}\b", re.IGNORECASE)
_CASE = re.compile(r"\bCASE-\d{4}\b", re.IGNORECASE)
_SHIPMENT = re.compile(r"\bSHP-\d+\b", re.IGNORECASE)
# A decision runs only when the whole message is the command, so "do not approve VAL-0002" or
# "should I approve VAL-0002?" changes nothing; any other mention lists the decisions instead.
_APPROVE_COMMAND = re.compile(r"^\s*approve\s+(VAL-\d{4})\s*[.!]?\s*$", re.IGNORECASE)
_REJECT_COMMAND = re.compile(r"^\s*reject\s+(VAL-\d{4})(?:\s*[,:]?\s*(?:because|reason:?|due to)\s+(.+?))?\s*$",
                             re.IGNORECASE | re.DOTALL)
_DECISIONS = re.compile(r"\b(?:approv\w*|reject\w*|decision\w*|decide|pending)\b", re.IGNORECASE)
_STATUS = re.compile(r"\b(?:status|update|progress|plan|recommend\w*|happening|where are we)\b", re.IGNORECASE)
_DETAILS = re.compile(r"\b(?:details?|detailed)\b", re.IGNORECASE)
_LIST_CASES = re.compile(r"\b(?:list|show)\s+(?:the\s+)?(?:(?:all|open)\s+)?cases\b", re.IGNORECASE)


@dataclass(frozen=True)
class Command:
    """What the planner asked for: start, approve, reject, decisions, status, details, list, or help."""

    kind: str
    event_id: str | None = None
    validation_id: str | None = None
    case_id: str | None = None
    shipment_id: str | None = None
    reason: str | None = None


def interpret(text: str, event_ids: list[str]) -> Command:
    """Match a message to a command by IDs and keywords. Exact approve and reject commands come first."""
    case = _match(_CASE, text)
    shipment = _match(_SHIPMENT, text)
    if approve := _APPROVE_COMMAND.match(text):
        return Command("approve", validation_id=approve.group(1).upper())
    if reject := _REJECT_COMMAND.match(text):
        reason = reject.group(2).strip() if reject.group(2) else None
        return Command("reject", validation_id=reject.group(1).upper(), reason=reason)
    if _DECISIONS.search(text):
        return Command("decisions")
    event = next((e for e in event_ids if e.lower() in text.lower()), None)
    if event:
        return Command("start", event_id=event)
    if _LIST_CASES.search(text):
        return Command("list")
    if _DETAILS.search(text):
        return Command("details", case_id=case, shipment_id=shipment)
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
            if command.kind == "decisions":
                return self.decisions()
            if command.kind == "list":
                return self.list_cases()
            if command.kind in ("status", "details"):
                case_id = command.case_id or self._latest_case(command.shipment_id)
                if case_id is None:
                    if command.shipment_id:
                        return self.shipment_status(command.shipment_id, events)
                    return self._help(events, f"There is no case for {command.shipment_id or 'any shipment'} yet.")
                return self.describe(case_id, detailed=command.kind == "details")
        except RuntimeError as error:  # An agent run is already in progress.
            return f"{error}\n\n{self.describe(self._latest_case())}"
        except LookupError as error:
            return self._help(events, str(error))
        return self._help(events)

    def list_cases(self) -> str:
        """List recorded cases without starting agents; decisions come before monitoring."""
        priority = {"needs_human_decision": 0, "awaiting_approval": 1,
                    "analyzing": 2, "executing": 2, "monitoring": 3}
        with self.clear.snapshot():
            cases = self.clear.list_cases()
            if not cases:
                return ("**Cases**\n\nNo cases have been created yet. "
                        "Use `help` to see available events, or `status of SHP-1001` to inspect a shipment.")
            # Stable sorting preserves newest-first order within each priority.
            cases = sorted(cases, key=lambda c: priority.get(c["status"], 4))
            rows = []
            for case in cases:
                shipment = read.get_shipment(self.clear.store, case["shipment_id"])
                exception = shipment.get("exception") or {}
                label = view.STATUS.get(case["status"], (case["status"], ""))[0]
                rows.append(f"**{case['case_id']} · {case['shipment_id']} · {label}**\n"
                            f"  Exception: {exception.get('description') or exception.get('type') or 'None recorded'}\n"
                            f"  Open: `status {case['case_id']}`")
        return (_section("Cases", _bullets(rows)) +
                "\n\nCases needing a human decision or approval appear first. Monitoring cases remain listed.")

    def decisions(self) -> str:
        """Transfers awaiting approval and cases awaiting a human decision, with the exact commands.

        Read-only: a message that mentions a decision without being the exact command lands here.
        """
        rows = []
        with self.clear.snapshot():
            for case in self.clear.list_cases():
                if case["status"] == "needs_human_decision":
                    reason = self.clear.get_case(case["case_id"])["status_reason"]
                    rows.append(f"**{case['case_id']} · {case['shipment_id']} · Needs a human decision**\n"
                                f"  {reason}\n  Open: `details {case['case_id']}`")
                if case["status"] != "awaiting_approval":
                    continue
                plan = self.clear.get_case(case["case_id"])["plan"]
                recommended = next((r for r in view.option_rows(plan) if r["recommended"]), None)
                for action in plan["actions"]:
                    if action["status"] != "awaiting_approval":
                        continue
                    validation, validation_id = action["validation"], action["validation_id"]
                    lines = [f"**{validation_id} · {case['case_id']} · {case['shipment_id']}**",
                             f"  Transfer: {validation['quantity']:g} t from plant {validation['source_plant']} "
                             f"to plant {validation['destination_plant']}"]
                    if recommended:
                        lines.append(f"  Recommended: {recommended['option']}; "
                                     f"deferred orders: {recommended['deferred_orders']}")
                    lines += [f"  To approve: `approve {validation_id}`",
                              f"  To reject: `reject {validation_id} because your reason`"]
                    rows.append("\n".join(lines))
        if not rows:
            return _section("Decisions", "Nothing is waiting for your decision.") + \
                "\n\nTo see every case: `list cases`."
        return (_section("Decisions waiting for you", _bullets(rows)) +
                "\n\nApprovals and rejections run only on these exact commands; a question or a sentence "
                "such as \"do not approve\" changes nothing.")

    def shipment_status(self, shipment_id: str, events: list[dict]) -> str:
        """Read the recorded shipment before a case exists, without submitting an event."""
        with self.clear.snapshot():
            shipment = read.get_shipment(self.clear.store, shipment_id)
        exception = shipment.get("exception") or {}
        paragraphs = [_section(f"{shipment_id} · Shipment status", _bullets([
            f"Status: {shipment['status']}",
            f"Purchase order: {shipment['purchase_order']}",
            f"Destination port: {shipment['port_of_discharge']}",
            f"ETA: {shipment['eta']}",
            f"Recorded exception: {exception.get('description') or exception.get('type') or 'None'}",
        ])), "No case has been created for this shipment. Analysis has not started."]
        if shipment.get("events"):
            latest = shipment["events"][-1]
            paragraphs.append(_section("Latest recorded event",
                                       f"{latest['event_id']}: {latest['description']}"))
        recorded = {event["event_id"] for event in shipment.get("events", [])}
        available = [e for e in events if e["shipment_id"] == shipment_id and e["event_id"] not in recorded]
        if available:
            paragraphs.append(_section("Prepared demo events", _bullets(
                f"{event['event_id']}: {event['description']}" for event in available)))
            paragraphs.append("These events have not been submitted. To submit the next demo event and start "
                              f"CLEAR's analysis: `work {available[0]['event_id']}`.")
        else:
            paragraphs.append("There are no new prepared demo events for this shipment.")
        return "\n\n".join(paragraphs)

    def describe(self, case_id: str, detailed: bool = False) -> str:
        """A scannable Markdown summary, with full evidence and rationale available on request.

        All metrics come from the rendered plan's records. Formatting does
        not call a model or change the case, its actions, or its approval.
        """
        with self.clear.snapshot():
            case = self.clear.get_case(case_id.upper())
            log = self.clear.get_case_log(case["case_id"])
        label, _ = view.STATUS[case["status"]]
        paragraphs = [f"**{case['case_id']} · {case['shipment_id']} · {label}**"]
        plan = case["plan"]
        if case["running"] and case["status"] in ("analyzing", "executing"):
            paragraphs.append(_section("Work in progress", "The agents are working. Latest steps:\n\n" +
                                      _bullets(f"{e['actor']}: {e['summary']}" for e in log[-LOG_LINES:])))
            paragraphs.append(f"Check again in a minute: `status of {case['shipment_id']}`.")
            return "\n\n".join(paragraphs)
        if case["status_reason"] and not (plan and plan["escalation"] == case["status_reason"]):
            paragraphs.append(_section("Case update", case["status_reason"]))
        if not plan:
            return "\n\n".join(paragraphs)

        exception = case["shipment"].get("exception") or {}
        paragraphs.append(_section("Situation", exception.get("description") or plan["exception"]))
        prediction = plan["impact"]["prediction"]
        rows = view.option_rows(plan)
        facts = [f"Predicted resolution: **{prediction['predicted_days']:g} days**",
                 f"Prediction source: {view.prediction_note(prediction)}",
                 f"Current coverage: {_coverage(rows[0])}"]
        paragraphs.append(_section("Supply impact", _bullets(facts)))
        recommended = next((r for r in rows if r["recommended"]), None)
        if recommended:
            paragraphs.append(_section("Recommended course", f"**{recommended['option']}**\n\n" + _bullets([
                f"Orders served: {recommended['orders_served']}",
                f"Transfer: {recommended['transfer'] if recommended['transfer'] != '—' else 'No new transfer'}",
                f"Coverage for selected demand: {_coverage(recommended)}",
                f"Deferred orders: {recommended['deferred_orders']}",
            ])))
        elif plan["recommendation"]:
            # Preserve the explanation when the plan is kept or no option is feasible.
            paragraphs.append(_section("Recommended course", plan["recommendation"]))
        for action in plan["actions"]:
            validation = action["validation"]
            move = (f"{validation['quantity']:g} t from plant {validation['source_plant']} "
                    f"to plant {validation['destination_plant']}")
            if action["status"] == "awaiting_approval":
                if case["status"] != "awaiting_approval":
                    paragraphs.append(_section("Transfer status",
                                      f"`{action['validation_id']}` is not currently accepting approval. "
                                      "Review the case update and decision required."))
                    continue
                paragraphs.append(_section("Approval required", _bullets([
                    f"Transfer: **{move}**",
                    f"Validation: `{action['validation_id']}` - passed the business rules",
                ]) + f"\n\nTo approve: `approve {action['validation_id']}`"
                     f"\n\nTo reject: `reject {action['validation_id']} because your reason`"))
            elif action["sto"]:
                approval = action["approval"]
                paragraphs.append(_section("Transfer recorded",
                                  f"STO {action['sto']['purchase_order']} created: {move} ({action['validation_id']}, "
                                  f"{approval['approval_id']} by {approval['approver']}).\n\n"
                                  "The stock is in transit; this does not confirm physical receipt."))
        if plan["escalation"]:
            # Keep the full human-decision requirement, including in the short view.
            paragraphs.append(_section("Decision required", plan["escalation"]))
        if plan["next_check"]:
            paragraphs.append(_section("Follow-up", _follow_up(plan["next_check"])))
        if detailed:
            paragraphs.append(_section("Evidence and rationale", plan["exception"]))
            if plan["evidence"]:
                paragraphs.append(_bullets(f"{e['fact']} (source: {e['source']})" for e in plan["evidence"]))
            if recommended and plan["recommendation"]:
                paragraphs.append(plan["recommendation"])
            options = [f"**{row['option']}**: {_coverage(row)}; orders served: {row['orders_served']}; "
                       f"transfer: {row['transfer']}; deferred orders: {row['deferred_orders']}; "
                       f"validation: {row['validation']}; assessment: `{row['assessment_id']}`"
                       for row in rows]
            paragraphs.append(_section("Assessed options", _bullets(options)))
        else:
            paragraphs.append(f"For full evidence, rationale, and assessed options: `details {case['case_id']}`.")
        return "\n\n".join(paragraphs)

    def _start(self, command: Command, events: list[dict]) -> str:
        event_id = command.event_id or self._next_event(command.shipment_id, events)
        case_id = self.clear.send_event(event_id)
        self.clear.wait(self.wait_seconds)
        return self.describe(case_id)

    def _decide(self, command: Command) -> str:
        pending = self._pending()
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
            "list cases needing attention, for example: show open cases or list cases",
            "start an event from the logistics feed, for example: work S1-DOC-HOLD",
            "inspect a shipment before analysis or read its case status: status of SHP-1001",
            "read the full evidence and assessed options, for example: details CASE-0001",
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
            AgentSkill(id="list-cases", name="List cases",
                       description="Lists recorded cases, with human decisions and approvals first.",
                       tags=["cases", "planner inbox"], examples=["Show open cases", "List cases"]),
            AgentSkill(id="work-exception", name="Work a shipment exception",
                       description="Starts the agents on an event from the logistics feed.",
                       tags=["shipment exception", "customs hold", "port congestion"],
                       examples=["Work S1-DOC-HOLD", "SHP-1002 is delayed by yard congestion"]),
            AgentSkill(id="case-status", name="Case status",
                       description="Recorded shipment status before analysis; case status, predicted resolution "
                                   "time, and the recommended option when a case exists.",
                       tags=["status", "recovery plan"], examples=["Status of SHP-1001", "Details of SHP-1001"]),
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
    outcome = "covered" if row["covered"] else f"**{row['shortage_t']:g} t short**"
    return f"**{row['coverage_days']:g} / {row['needed_days']:g} days** - {outcome}"


def _section(title: str, content: str) -> str:
    return f"**{title}**\n\n{content}"


def _follow_up(text: str) -> str:
    """Use actual numbered Markdown with spacing, preserving all follow-up text."""
    return re.sub(r"\n(?=\d+\.\s)", "\n\n", format_points(text))


def _bullets(items) -> str:
    return "\n".join(f"- {item}" for item in items)


def _match(pattern: re.Pattern, text: str) -> str | None:
    found = pattern.search(text)
    return found.group(0).upper() if found else None
