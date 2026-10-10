"""Running a case (docs/PLAN.md §2, §6c).

Agents are built fresh for every run and bound to one case. Each agent gets
its own case-log hooks, because Strands does not pass the orchestrator's
invocation state on to the specialists it calls as tools. Tools run one at
a time, so the JSON store keeps a single writer.

A run either works a new logistics event or executes a human approval. The
first run of a case ends with the validated STO awaiting approval; the
approval starts the run that creates the STO and verifies stock.
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass

from strands import Agent
from strands.models import BedrockModel
from strands.models.model import Model
from strands.tools.executors import SequentialToolExecutor

from clear_agents import caselog, prompts, tools
from clear_agents.plan import RecoveryPlan, check_references
from clear_tools.approvals import record_approval
from clear_tools.events import record_event
from clear_tools.store import JsonStore

ModelFactory = Callable[[str], Model]  # Role (orchestrator, evidence, impact, action) -> model.


def bedrock_model(role: str) -> Model:
    """One mid-size Bedrock model for every agent (docs/PLAN.md §8b)."""
    model_id = os.environ.get("CLEAR_BEDROCK_MODEL_ID")
    if not model_id:
        raise LookupError("Set CLEAR_BEDROCK_MODEL_ID to a model available in Bedrock us-west-2 (see .env.example).")
    return BedrockModel(model_id=model_id, region_name=os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))


@dataclass(frozen=True)
class Agents:
    orchestrator: Agent
    evidence: Agent
    impact: Agent
    action: Agent


def build_agents(store: JsonStore, case_id: str, model_for: ModelFactory) -> Agents:
    def agent(role: str, name: str, actor: str, prompt: str, agent_tools: list, description: str | None = None):
        return Agent(
            name=name,
            description=description,
            system_prompt=prompt,
            tools=agent_tools,
            model=model_for(role),
            hooks=[caselog.CaseLogHooks(store, case_id, actor)],
            tool_executor=SequentialToolExecutor(),
            callback_handler=None,
        )

    evidence = agent("evidence", "evidence_agent", "Evidence", prompts.EVIDENCE, tools.evidence_tools(store),
                     "Facts about a shipment exception: shipment, purchase order, documents, inventory, "
                     "and document reconciliation.")
    impact = agent("impact", "impact_agent", "Impact & Options", prompts.IMPACT, tools.impact_tools(store),
                   "Resolution-time prediction and scoring of recovery options.")
    action = agent("action", "action_agent", "Action", prompts.ACTION, tools.action_tools(store),
                   "Validates stock transport orders, creates an approved STO, and verifies stock positions.")
    orchestrator = agent("orchestrator", "orchestrator", "Orchestrator", prompts.ORCHESTRATOR,
                         [evidence.as_tool(), impact.as_tool(), action.as_tool()])
    return Agents(orchestrator, evidence, impact, action)


def open_case_for_event(store: JsonStore, event: dict) -> str:
    """Record the event, open the shipment's case (or reuse it), and log the event. No LLM."""
    record_event(store, event)
    case_id = caselog.open_case(store, event["shipment_id"])["case_id"]
    caselog.update_case(store, case_id, status="analyzing", status_reason=None)
    caselog.log(store, case_id, "Event feed", "event", event["description"],
                source="logistics event feed (simulated)", event_id=event["event_id"])
    return case_id


def work_event(store: JsonStore, case_id: str, event: dict, model_for: ModelFactory = bedrock_model) -> dict:
    case = caselog.get_case(store, case_id)
    prompt = (f"Case {case_id} for shipment {case['shipment_id']}.\n"
              f"New event {event['event_id']} ({event['type']}) at {event['occurred_at']}: {event['description']}\n")
    if case["plan"]:
        prompt += f"Plan before this event (its IDs refer to earlier results):\n{json.dumps(case['plan'])}\n"
    return _run(store, case_id, prompt + "Work the case and return the recovery plan.", model_for)


def decide(store: JsonStore, case_id: str, validation_id: str, approver: str, decision: str,
           reason: str | None = None) -> dict:
    """Record a human decision on a validated STO and update the case. No LLM."""
    approval = record_approval(store, validation_id, approver, decision, reason)
    summary = f"{decision.capitalize()} {validation_id}" + (f": {reason}" if reason else "")
    caselog.log(store, case_id, approver, "approval", summary, approval_id=approval["approval_id"])
    if decision == "rejected":
        caselog.update_case(store, case_id, status="needs_human_decision",
                            status_reason=f"Rejected by {approver}: {reason}")
    else:
        caselog.update_case(store, case_id, status="executing", status_reason=None)
    return approval


def work_approval(store: JsonStore, case_id: str, approval: dict, model_for: ModelFactory = bedrock_model) -> dict:
    case = caselog.get_case(store, case_id)
    prompt = (f"Case {case_id} for shipment {case['shipment_id']}: {approval['approver']} approved "
              f"{approval['validation_id']} (approval_id {approval['approval_id']}).\n"
              "Ask action_agent to create the stock transport order with these two IDs and to verify stock "
              "positions. Then return the updated recovery plan with that action marked executed.\n"
              f"Plan before the approval:\n{json.dumps(case['plan'])}")
    return _run(store, case_id, prompt, model_for)


def _run(store: JsonStore, case_id: str, prompt: str, model_for: ModelFactory) -> dict:
    shipment_id = caselog.get_case(store, case_id)["shipment_id"]
    try:
        orchestrator = build_agents(store, case_id, model_for).orchestrator
        plan = orchestrator(prompt, structured_output_model=RecoveryPlan).structured_output
        problems = check_references(store, plan, shipment_id)
        if problems:
            caselog.log(store, case_id, "Plan check", "error", "Plan cites invalid IDs: " + "; ".join(problems),
                        flag="error")
            retry = f"Your plan cites invalid IDs: {'; '.join(problems)}. Fix the plan and return it again."
            plan = orchestrator(retry, structured_output_model=RecoveryPlan).structured_output
            problems = check_references(store, plan, shipment_id)
        if problems:
            return _fail(store, case_id, "Plan cites invalid IDs: " + "; ".join(problems))
    except Exception as error:  # A failed run must leave a readable case, never a stuck one.
        return _fail(store, case_id, f"{type(error).__name__}: {error}")

    status, reason = _status(plan)
    caselog.log(store, case_id, "Orchestrator", "status", f"Status: {status}" + (f" ({reason})" if reason else ""))
    return caselog.update_case(store, case_id, plan=plan.model_dump(), status=status, status_reason=reason)


def _status(plan: RecoveryPlan) -> tuple[str, str | None]:
    if any(action.status == "awaiting_approval" for action in plan.actions):
        return "awaiting_approval", None
    if plan.escalation:
        return "needs_human_decision", plan.escalation
    return "monitoring", None


def _fail(store: JsonStore, case_id: str, reason: str) -> dict:
    caselog.log(store, case_id, "CLEAR", "error", reason, flag="error")
    return caselog.update_case(store, case_id, status="needs_human_decision", status_reason=reason)
