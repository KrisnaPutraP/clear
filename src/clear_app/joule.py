"""Joule front door: CLEAR as an A2A agent that SAP Joule calls.

Joule's agent-request action forwards the planner's message over A2A
(protocol 0.3.0) and gives the agent 60 seconds to answer. Agent runs often
take longer, so a new exception starts the agents in the background and the
planner asks for the status in later messages; each answer waits up to
WAIT_SECONDS for a run to end.

Claude reads what the planner means (clear_app.joule_intent); the keyword
rules in interpret() take over when it is unavailable. Neither can change a
case: an approval or a rejection only leads to a preview with a confirmation
code, and only a message that carries that code, normally the Confirm
button, records the decision. The answer is text built from the case and its
records, so every number has the same source as in the UI; two buttons ride
along as a data part that the Joule function renders.
"""

import asyncio
import base64
import hmac
import logging
import re
import secrets
import threading
import time
from dataclasses import dataclass

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, DataPart, Part, TextPart
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError, UnsupportedOperationError
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse

from clear_agents.plan import format_points
from clear_app import view
from clear_app.contract import Clear
from clear_app.joule_intent import Intent
from clear_tools import read

APPROVER = "Planner via Joule"
WAIT_SECONDS = 40  # Joule waits 60 s for an answer; leave room for the network and the reply.
LOG_LINES = 4  # Latest timeline steps shown while a run is in progress.
CONFIRM_SECONDS = 600  # How long a confirmation code stays valid.
_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789"  # No vowels, so a code never spells a word.

log = logging.getLogger("clear.joule")

_VALIDATION = re.compile(r"\bVAL-\d{4}\b", re.IGNORECASE)
_CASE = re.compile(r"\bCASE-\d{4}\b", re.IGNORECASE)
_SHIPMENT = re.compile(r"\bSHP-\d+\b", re.IGNORECASE)
# Keyword rules, used when the model is unavailable. Only a message that is exactly the command asks to
# approve or reject; any other mention lists the decisions. Either way the decision still needs confirming.
_APPROVE_COMMAND = re.compile(r"^\s*approve\s+(VAL-\d{4})\s*[.!]?\s*$", re.IGNORECASE)
_REJECT_COMMAND = re.compile(r"^\s*reject\s+(VAL-\d{4})(?:\s*[,:]?\s*(?:because|reason:?|due to)\s+(.+?))?\s*$",
                             re.IGNORECASE | re.DOTALL)
_HOLD = re.compile(r"\b(?:do not|don't|dont|not yet|cancel|keep \S+ waiting|wait|hold|jangan|tunggu|batal)\b",
                   re.IGNORECASE)
_DECISIONS = re.compile(r"\b(?:approv\w*|reject\w*|decision\w*|decide|pending)\b", re.IGNORECASE)
_STATUS = re.compile(r"\b(?:status|update|progress|plan|recommend\w*|happening|where are we)\b", re.IGNORECASE)
_DETAILS = re.compile(r"\b(?:details?|detailed)\b", re.IGNORECASE)
_LIST_CASES = re.compile(r"\b(?:list|show)\s+(?:the\s+)?(?:(?:all|open)\s+)?cases\b", re.IGNORECASE)


@dataclass(frozen=True)
class Command:
    """What the planner asked for: start, approve, reject, hold, question, decisions, status, details, list,
    or help."""

    kind: str
    event_id: str | None = None
    validation_id: str | None = None
    case_id: str | None = None
    shipment_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Button:
    title: str
    value: str  # Joule sends it back as the planner's next message.


@dataclass(frozen=True)
class Reply:
    """An answer: Markdown text, and two buttons the Joule function renders below it."""

    text: str
    buttons: tuple[Button, Button] | None = None
    buttons_title: str = "Next step"


@dataclass(frozen=True)
class Confirmation:
    """A decision the planner asked for and has not confirmed yet."""

    validation_id: str
    case_id: str
    decision: str  # approved or rejected
    reason: str | None
    code: str
    expires: float


def interpret(text: str, event_ids: list[str]) -> Command:
    """Match a message to a command by IDs and keywords: the fallback when the model is unavailable."""
    case = _match(_CASE, text)
    shipment = _match(_SHIPMENT, text)
    if approve := _APPROVE_COMMAND.match(text):
        return Command("approve", validation_id=approve.group(1).upper())
    if reject := _REJECT_COMMAND.match(text):
        reason = reject.group(2).strip() if reject.group(2) else None
        return Command("reject", validation_id=reject.group(1).upper(), reason=reason)
    event = next((e for e in event_ids if e.lower() in text.lower()), None)
    if event:  # Before the hold words: an event ID such as S1-DOC-HOLD contains one.
        return Command("start", event_id=event)
    if _HOLD.search(text):
        return Command("hold", validation_id=_match(_VALIDATION, text))
    if _DECISIONS.search(text):
        return Command("decisions")
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

    def __init__(self, clear: Clear, approver: str = APPROVER, wait_seconds: float = WAIT_SECONDS,
                 understand=None):
        self.clear, self.approver, self.wait_seconds = clear, approver, wait_seconds
        self.understand = understand  # joule_intent.ClaudeUnderstanding, or None for the keyword rules.
        self._confirmations: dict[str, Confirmation] = {}
        self._lock = threading.Lock()

    def answer(self, text: str) -> str:
        return self.respond(text).text

    def respond(self, text: str) -> Reply:
        with self.clear.snapshot():
            events = self.clear.list_events()
        command = self._command(text, events)
        confirmation = self._confirmation_in(text)
        try:
            if confirmation:
                if command.kind == "hold":
                    return self._hold(confirmation.validation_id)
                return self._confirm(confirmation)
            if command.kind == "start":
                return self._start(command, events)
            if command.kind in ("approve", "reject"):
                return self._preview(command)
            if command.kind == "hold":
                return self._hold(command.validation_id)
            if command.kind == "decisions":
                return self.decisions()
            if command.kind == "list":
                return Reply(self.list_cases())
            if command.kind in ("status", "details", "question"):
                case_id = command.case_id or self._case_for(command)
                if case_id is None:
                    if command.shipment_id:
                        return Reply(self.shipment_status(command.shipment_id, events))
                    return Reply(self._help(events,
                                            f"There is no case for {command.shipment_id or 'any shipment'} yet."))
                return self._case_reply(case_id, detailed=command.kind != "status")
        except RuntimeError as error:  # An agent run is already in progress.
            return Reply(f"{error}\n\n{self.describe(self._latest_case())}")
        except LookupError as error:
            return Reply(self._help(events, str(error)))
        return Reply(self._help(events))

    def _command(self, text: str, events: list[dict]) -> Command:
        """The model's reading of the message, or the keyword rules when it has none or is unsure (help)."""
        command, source = None, "rules"
        if self.understand:
            intent = self.understand(text, self._context(events))
            if intent and intent.kind != "help":
                command, source = self._from_intent(intent, events), "model"
        if command is None:
            command = interpret(text, [e["event_id"] for e in events])
        log.info("Joule message %r -> %s (%s)", text[:300], command, source)
        return command

    def _context(self, events: list[dict]) -> dict:
        """What the model may refer to: open cases, transfers awaiting approval, prepared events."""
        with self.clear.snapshot():
            cases = [{k: c[k] for k in ("case_id", "shipment_id", "status")} for c in self.clear.list_cases()]
        transfers = [{"validation_id": validation_id, "case_id": case_id, "transfer": move}
                     for validation_id, (case_id, move) in self._awaiting().items()]
        return {"cases": cases, "transfers_awaiting_approval": transfers,
                "events": [{k: e[k] for k in ("event_id", "shipment_id", "description")} for e in events]}

    def _from_intent(self, intent: Intent, events: list[dict]) -> Command:
        """The model's intent as a command, keeping only IDs that exist."""
        with self.clear.snapshot():
            cases = self.clear.list_cases()
        shipments = {c["shipment_id"] for c in cases} | {e["shipment_id"] for e in events}

        def known(value: str | None, ids: set[str]) -> str | None:
            return value.strip().upper() if value and value.strip().upper() in ids else None

        validation = intent.validation_id.strip().upper() if intent.validation_id and _VALIDATION.fullmatch(
            intent.validation_id.strip()) else None
        return Command(intent.kind, event_id=known(intent.event_id, {e["event_id"] for e in events}),
                       validation_id=validation, case_id=known(intent.case_id, {c["case_id"] for c in cases}),
                       shipment_id=known(intent.shipment_id, shipments), reason=intent.reason or None)

    def _preview(self, command: Command) -> Reply:
        """Ask the planner to confirm an approval or a rejection. Changes nothing."""
        awaiting = self._awaiting()
        validation_id = command.validation_id
        if validation_id and validation_id not in awaiting:
            return self.decisions(note=f"`{validation_id}` is not awaiting approval.")
        if validation_id is None:
            if len(awaiting) != 1:
                return self.decisions(note="Which transfer do you mean?" if awaiting else None)
            validation_id = next(iter(awaiting))
        if command.kind == "reject" and not command.reason:
            return Reply(f"Why do you reject `{validation_id}`? Tell me the reason, for example: "
                         f"`reject {validation_id} because the plant needs the stock`.")
        case_id, move = awaiting[validation_id]
        decision, verb = ("approved", "approval") if command.kind == "approve" else ("rejected", "rejection")
        code = self._new_code()
        with self._lock:
            self._confirmations[validation_id] = Confirmation(validation_id, case_id, decision, command.reason,
                                                              code, time.monotonic() + CONFIRM_SECONDS)
        lines = [f"Transfer: {move}", f"Case: {case_id}"] + self._recommended_lines(case_id)
        if command.reason:
            lines.append(f"Reason: {command.reason}")
        effect = ("creates the stock transport order" if decision == "approved"
                  else "records the rejection and hands the case to a human decision")
        confirm = f"Confirm {verb} of {validation_id}, code {code}"
        return Reply(_section(f"Confirm {verb} · {validation_id}", _bullets(lines)) +
                     f"\n\nNothing has changed yet. **Confirm {verb}** {effect}; **Cancel** keeps "
                     f"`{validation_id}` waiting.\n\nWithout buttons, reply: `{confirm}`",
                     (Button(f"Confirm {verb}", confirm), Button("Cancel", f"Cancel, keep {validation_id} waiting")),
                     buttons_title=f"Confirm the {verb} of {validation_id}?")

    def _confirm(self, confirmation: Confirmation) -> Reply:
        """Record the decision the planner confirmed, if it is still current."""
        with self._lock:
            current = self._confirmations.pop(confirmation.validation_id, None)
        if (current != confirmation or time.monotonic() > confirmation.expires
                or confirmation.validation_id not in self._awaiting()):
            return self.decisions(note="That confirmation is no longer valid, so nothing changed.")
        self.clear.submit_decision(confirmation.case_id, confirmation.validation_id, self.approver,
                                   confirmation.decision, confirmation.reason)
        self.clear.wait(self.wait_seconds)
        return self._case_reply(confirmation.case_id, detailed=False)

    def _hold(self, validation_id: str | None) -> Reply:
        """Keep a transfer waiting: drop its confirmation. Changes nothing in the case."""
        with self._lock:
            if validation_id:
                self._confirmations.pop(validation_id, None)
            else:
                self._confirmations.clear()
        awaiting = self._awaiting()
        target = validation_id if validation_id in awaiting else (
            next(iter(awaiting)) if len(awaiting) == 1 else None)
        text = "Okay, nothing changed."
        if target:
            text += f" `{target}` is still waiting for your decision."
        return Reply(text, self._decision_buttons(target) if target else None)

    def _confirmation_in(self, text: str) -> Confirmation | None:
        with self._lock:
            return next((c for c in self._confirmations.values()
                         if re.search(rf"\b{c.code}\b", text, re.IGNORECASE)), None)

    @staticmethod
    def _new_code() -> str:
        while True:
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
            if any(ch.isdigit() for ch in code) and not code.isdigit():
                return code

    def _awaiting(self) -> dict[str, tuple[str, str]]:
        """Transfers awaiting approval: validation ID -> (case ID, the transfer in words)."""
        awaiting = {}
        with self.clear.snapshot():
            for case in self.clear.list_cases():
                if case["status"] != "awaiting_approval":
                    continue
                plan = self.clear.get_case(case["case_id"])["plan"] or {"actions": []}
                for action in plan["actions"]:
                    if action["status"] == "awaiting_approval":
                        validation = action["validation"]
                        awaiting[action["validation_id"]] = (
                            case["case_id"], f"{validation['quantity']:g} t from plant {validation['source_plant']} "
                                             f"to plant {validation['destination_plant']}")
        return awaiting

    def _recommended_lines(self, case_id: str) -> list[str]:
        with self.clear.snapshot():
            plan = self.clear.get_case(case_id)["plan"]
        recommended = next((r for r in view.option_rows(plan) if r["recommended"]), None) if plan else None
        if not recommended:
            return []
        return [f"Recommended: {recommended['option']}", f"Deferred orders: {recommended['deferred_orders']}"]

    def _case_for(self, command: Command) -> str | None:
        awaiting = self._awaiting()
        if command.validation_id in awaiting:
            return awaiting[command.validation_id][0]
        return self._latest_case(command.shipment_id)

    def _case_reply(self, case_id: str, detailed: bool) -> Reply:
        return Reply(self.describe(case_id, detailed=detailed), self._case_buttons(case_id))

    def _case_buttons(self, case_id: str) -> tuple[Button, Button] | None:
        with self.clear.snapshot():
            case = self.clear.get_case(case_id.upper())
        if case["running"] and case["status"] in ("analyzing", "executing"):
            return (Button("Refresh status", f"status of {case['shipment_id']}"),
                    Button("What needs my decision?", "What needs my decision?"))
        awaiting = [v for v, (c, _) in self._awaiting().items() if c == case["case_id"]]
        return self._decision_buttons(awaiting[0]) if awaiting else None

    @staticmethod
    def _decision_buttons(validation_id: str) -> tuple[Button, Button]:
        return (Button(f"Approve {validation_id}", f"Approve {validation_id}"),
                Button(f"Reject {validation_id}", f"Reject {validation_id}"))

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

    def decisions(self, note: str | None = None) -> Reply:
        """Transfers awaiting approval and cases awaiting a human decision. Read-only."""
        rows, first = [], None
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
                    first = first or validation_id
                    lines = [f"**{validation_id} · {case['case_id']} · {case['shipment_id']}**",
                             f"  Transfer: {validation['quantity']:g} t from plant {validation['source_plant']} "
                             f"to plant {validation['destination_plant']}"]
                    if recommended:
                        lines.append(f"  Recommended: {recommended['option']}; "
                                     f"deferred orders: {recommended['deferred_orders']}")
                    lines += [f"  To approve: `approve {validation_id}`",
                              f"  To reject: `reject {validation_id} because your reason`"]
                    rows.append("\n".join(lines))
        lead = f"{note}\n\n" if note else ""
        if not rows:
            return Reply(lead + _section("Decisions", "Nothing is waiting for your decision.") +
                         "\n\nTo see every case: `list cases`.")
        return Reply(lead + _section("Decisions waiting for you", _bullets(rows)) +
                     "\n\nApproving or rejecting asks you to confirm first; nothing changes until you do.",
                     self._decision_buttons(first) if first else None)

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

    def _start(self, command: Command, events: list[dict]) -> Reply:
        event_id = command.event_id or self._next_event(command.shipment_id, events)
        case_id = self.clear.send_event(event_id)
        self.clear.wait(self.wait_seconds)
        return self._case_reply(case_id, detailed=False)

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
            "see what needs your decision: what needs my decision?",
            "approve or reject a validated transfer, in your own words; you confirm before anything changes",
        ]))
        paragraphs.append("Events in the feed:")
        paragraphs.append(_bullets(f"{e['event_id']} ({e['shipment_id']}): {e['description']}" for e in events))
        latest = self._latest_case()
        if latest:
            paragraphs.append(f"Latest case: {self.describe(latest).splitlines()[0]}")
        return "\n\n".join(paragraphs)


class ClearExecutor(AgentExecutor):
    """One A2A task per message: CaseDesk answers, and the task completes with the answer.

    The answer text is the first artifact and the final status message; buttons, when there are any, are a
    second artifact with one data part that the Joule function renders as postback buttons.
    """

    def __init__(self, desk: CaseDesk):
        self.desk = desk

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task(context.message)
        if not context.current_task:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        reply = await asyncio.to_thread(self.desk.respond, context.get_user_input())
        await updater.add_artifact([Part(root=TextPart(text=reply.text))], name="clear_answer")
        if reply.buttons:
            primary, secondary = reply.buttons
            await updater.add_artifact([Part(root=DataPart(data={
                "title": reply.buttons_title,
                "primary": {"title": primary.title, "value": primary.value},
                "secondary": {"title": secondary.title, "value": secondary.value},
            }))], name="clear_buttons")
        await updater.complete(new_agent_text_message(reply.text, task.context_id, task.id))

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
              wait_seconds: float = WAIT_SECONDS, understand=None) -> Starlette:
    """The A2A server: the agent card at /.well-known/agent-card.json and JSON-RPC at /.

    understand reads the planner's message (joule_intent.ClaudeUnderstanding); without it, the keyword rules do.
    """
    desk = CaseDesk(clear, wait_seconds=wait_seconds, understand=understand)
    handler = DefaultRequestHandler(agent_executor=ClearExecutor(desk), task_store=InMemoryTaskStore())
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
