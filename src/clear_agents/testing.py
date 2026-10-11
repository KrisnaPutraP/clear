"""A scripted stand-in for the Bedrock model, for tests and UI development only.

ScriptedModel replays fixed turns (text and tool calls) in the Bedrock
stream format, so the real Strands agents, tools, hooks, and case log run
end to end without AWS. It decides nothing and must never stand in for the
model in the demo.

The S1 and S2 scripts reproduce the expected agent steps. They read the
store when a run starts, so record IDs line up whatever ran before.
ScriptedDirector picks the script for the step a case is at.
"""

import itertools
import json
import re
from dataclasses import dataclass, field

from strands.models.model import Model

from clear_agents import caselog
from clear_tools import read, records, s4, sto
from clear_tools.store import JsonStore

S1, S2 = "SHP-1001", "SHP-1002"


@dataclass
class Turn:
    text: str = ""
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)


class ScriptedModel(Model):
    _tool_use_ids = itertools.count(1)

    def __init__(self, turns: list[Turn]):
        self.turns = list(turns)

    def update_config(self, **model_config) -> None:
        pass

    def get_config(self) -> dict:
        return {}

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        raise NotImplementedError("The script delivers structured output as a tool call.")
        yield  # pragma: no cover

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        if not self.turns:
            raise AssertionError("ScriptedModel has no turns left")
        turn = self.turns.pop(0)
        yield {"messageStart": {"role": "assistant"}}
        if turn.text:
            yield {"contentBlockDelta": {"delta": {"text": turn.text}}}
            yield {"contentBlockStop": {}}
        for name, arguments in turn.tool_calls:
            tool_use_id = f"tooluse-{next(self._tool_use_ids)}"
            yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": tool_use_id, "name": name}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(arguments)}}}}
            yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use" if turn.tool_calls else "end_turn"}}


def scripted(script: dict[str, list[Turn]]):
    """A model factory that gives each role its turns from one fixed script."""
    return lambda role: ScriptedModel(script.get(role, []))


class ScriptedDirector:
    """A model factory that plays the script for the event or approval that started the run."""

    def __init__(self, store: JsonStore):
        self.store = store
        self._trigger_seq: int | None = None
        self._script: dict[str, list[Turn]] = {}

    def __call__(self, role: str) -> ScriptedModel:
        trigger = next(e for e in reversed(self.store.read(caselog.LOG)) if e["kind"] in ("event", "approval"))
        if trigger["seq"] != self._trigger_seq:
            builder = s1_approval if trigger["kind"] == "approval" else SCRIPTS[trigger["event_id"]]
            self._trigger_seq, self._script = trigger["seq"], builder(self.store)
        return ScriptedModel(self._script.get(role, []))


# Labelled lines in the generated documents, standing in for LLM extraction.
_LABELS = {
    "purchase_order": re.compile(r"Buyer PO No\.:?\s*(\d+)"),
    "material": re.compile(r"Buyer Material No\.:\s*(\S+)"),
    "quantity": re.compile(r"Quantity:\s*([\d,]+(?:\.\d+)?)\s*(MT)\b"),
}


def extract_fields(bundle: dict) -> list[dict]:
    """Fields from get_documents() output, as a correct LLM extraction would give them."""
    extractions = []
    for document in bundle["documents"]:
        for line in document["text"].splitlines():
            for name, pattern in _LABELS.items():
                match = pattern.search(line)
                if not match:
                    continue
                extraction = {"document_type": document["document_type"], "field": name,
                              "value": match.group(1), "quote": line.strip()}
                if name == "quantity":
                    extraction["value"] = float(match.group(1).replace(",", ""))
                    extraction["unit"] = match.group(2)
                extractions.append(extraction)
    return extractions


def _case(store: JsonStore, shipment_id: str) -> dict:
    """The shipment's open case; scripts are built after the run opened it."""
    return next(c for c in store.read(caselog.CASES) if c["shipment_id"] == shipment_id and c["status"] != "closed")


def _plan(**fields) -> dict:
    return {"options": [], "recommended_option": None, "actions": [], "escalation": None, **fields}


def s1_event(store: JsonStore) -> dict[str, list[Turn]]:
    """S1 exception: reconcile, quantify, rejected transfer, re-plan, validated STO awaiting approval."""
    prediction = records.next_id(store, "prediction")
    current, alone, prioritized = (records.next_id(store, "assessment", n) for n in (1, 2, 3))
    rejected, valid = (records.next_id(store, "validation", n) for n in (1, 2))
    risk = {"shipment_id": S1, "prediction_id": prediction}
    transfer = {**risk, "transfer_quantity_t": 20, "source_plant": "1200"}
    options = [
        {"name": "Transfer 20 t from 1200", "assessment_id": alone,
         "note": "The feasible transfer alone still leaves a shortage."},
        {"name": "Transfer 20 t from 1200 + critical and high orders", "assessment_id": prioritized,
         "validation_id": valid, "note": "Covers the requirement; normal-priority orders wait."},
    ]
    plan = _plan(
        case_id=_case(store, S1)["case_id"],
        exception="Customs document hold: the packing list states a lower quantity than the invoice and PO.",
        evidence=[{"fact": "Packing list quantity differs from the invoice and the purchase order.",
                   "source": "reconcile_documents"},
                  {"fact": "Plant 1200 holds the material above its safety stock.", "source": "get_inventory"}],
        prediction_id=prediction,
        current_plan_assessment_id=current,
        options=options,
        recommendation="Transfer the feasible quantity from plant 1200 and serve critical and high orders "
                       "until the shipment clears; the full transfer was rejected by the safety-stock rule.",
        recommended_option=options[1]["name"],
        actions=[{"validation_id": valid, "status": "awaiting_approval"}],
        next_check="Customs response to the corrected packing list, and the vessel ETA.",
    )
    return {
        "orchestrator": [
            Turn("A customs document hold: start with document reconciliation.",
                 [("evidence_agent", {"input": f"Shipment {S1} is on a customs document hold. Get the shipment, "
                                               "its purchase order, the material's inventory, and its documents; "
                                               "extract and reconcile the document fields."})]),
            Turn("The quantity discrepancy is confirmed. Quantify the impact.",
                 [("impact_agent", {"input": f"Predict the resolution time for {S1} and assess the current plan: "
                                             "all orders, no transfer."})]),
            Turn("There is a shortage and plant 1200 holds stock. Validate a transfer of the full shortage.",
                 [("action_agent", {"input": f"Validate an STO of 32 t from plant 1200 for {S1} "
                                             f"with prediction {prediction}."})]),
            Turn("Rejected by the safety-stock rule. Assess the feasible quantity, alone and with priorities.",
                 [("impact_agent", {"input": f"With {prediction} for {S1}, assess a 20 t transfer from plant 1200 "
                                             "serving all orders, and the same transfer serving critical_high orders."})]),
            Turn("The feasible transfer plus critical and high orders is covered. Validate it.",
                 [("action_agent", {"input": f"Validate an STO of 20 t from plant 1200 for {S1} "
                                             f"with prediction {prediction}."})]),
            Turn("", [("RecoveryPlan", plan)]),
        ],
        "evidence": [
            Turn("", [("get_shipment", {"shipment_id": S1}), ("get_purchase_order", {"purchase_order": "4500001021"}),
                      ("get_inventory", {"material": "CHEM-BX40"}), ("get_documents", {"shipment_id": S1})]),
            Turn("", [("reconcile_documents", {"shipment_id": S1,
                                               "extractions": extract_fields(read.get_documents(store, S1))})]),
            Turn("- The packing list quantity differs from the invoice and the PO (reconcile_documents).\n"
                 "- Plant 1200 holds CHEM-BX40 above its safety stock (get_inventory)."),
        ],
        "impact": [
            Turn("", [("predict_resolution_time", {"shipment_id": S1})]),
            Turn("", [("calculate_supply_risk", risk)]),
            Turn(f"{prediction} gives the resolution time. {current}: the current plan leaves a shortage."),
            Turn("", [("calculate_supply_risk", transfer),
                      ("calculate_supply_risk", {**transfer, "priority_level": "critical_high"})]),
            Turn(f"{alone}: the transfer alone is short. {prioritized}: with critical and high orders it is covered."),
        ],
        "action": [
            Turn("", [("validate_action", {**risk, "source_plant": "1200", "quantity_t": 32})]),
            Turn(f"{rejected} rejected: plant 1200 would fall below its safety stock."),
            Turn("", [("validate_action", {**risk, "source_plant": "1200", "quantity_t": 20})]),
            Turn(f"{valid} is valid."),
        ],
    }


def s1_approval(store: JsonStore) -> dict[str, list[Turn]]:
    """After the planner approves: create the STO, verify stock, mark the action executed."""
    approval = store.read("records/approvals")[-1]
    validation_id = approval["validation_id"]
    case = _case(store, records.get(store, "validation", validation_id)["shipment_id"])
    number = str(max(int(h["PurchaseOrder"]) for h in store.read(s4.PO_HEADERS)) + 1)
    executed = {**case["plan"], "next_check": "Arrival of the transfer at plant 1100, and the customs response.",
                "actions": [{"validation_id": validation_id, "status": "executed", "purchase_order": number}]}
    return {
        "orchestrator": [
            Turn("Approved: create the STO and verify stock.",
                 [("action_agent", {"input": f"Create the STO for {validation_id} with approval "
                                             f"{approval['approval_id']}, then verify stock positions for CHEM-BX40."})]),
            Turn("", [("RecoveryPlan", executed)]),
        ],
        "action": [
            Turn("", [("create_stock_transport_order",
                       {"validation_id": validation_id, "approval_id": approval["approval_id"]})]),
            Turn("", [("get_inventory", {"material": "CHEM-BX40"})]),
            Turn(f"STO {number} created; plant 1200 is at its safety stock and plant 1100 has the transfer in transit."),
        ],
    }


def s1_eta_slip(store: JsonStore) -> dict[str, list[Turn]]:
    """S1 ETA slip after the approved transfer: only critical orders fit; escalate emergency sourcing."""
    case = _case(store, S1)
    prediction = records.next_id(store, "prediction")
    current, high, critical = (records.next_id(store, "assessment", n) for n in (1, 2, 3))
    blocked = records.next_id(store, "validation")
    risk = {"shipment_id": S1, "prediction_id": prediction}
    executed = [{"validation_id": r["validation_id"], "status": "executed", "purchase_order": r["purchase_order"]}
                for r in store.read(sto.EXECUTED) if r["material"] == "CHEM-BX40"]
    options = [
        {"name": "Critical and high orders, transfer in transit", "assessment_id": high,
         "note": "No longer covers the longer resolution time."},
        {"name": "Critical orders only, transfer in transit", "assessment_id": critical,
         "note": "Covers the requirement; high and normal orders wait."},
    ]
    plan = _plan(
        case_id=case["case_id"],
        exception="Customs document hold, now with an ETA slip from berth congestion at Tanjung Priok.",
        evidence=[{"fact": "The vessel ETA moved back by one day and congestion is high.", "source": "event feed"},
                  {"fact": "Plant 1200 has no stock above its safety stock left to move.", "source": "validate_action"}],
        prediction_id=prediction,
        current_plan_assessment_id=current,
        options=options,
        recommendation="Serve critical orders only until the shipment clears; no further transfer is feasible.",
        recommended_option=options[1]["name"],
        actions=executed,
        escalation="Decide on emergency sourcing for the deferred high and normal orders.",
        next_check="Berthing of the vessel and customs release at Tanjung Priok.",
    )
    return {
        "orchestrator": [
            Turn("The ETA slipped with high congestion. Re-predict and re-assess.",
                 [("impact_agent", {"input": f"Predict the resolution time for {S1} again, and assess all orders, "
                                             "critical_high orders, and critical orders, counting the transfer in transit."})]),
            Turn("Critical and high orders no longer fit. Check whether more stock can move.",
                 [("action_agent", {"input": f"Validate a further STO of 10 t from plant 1200 for {S1} "
                                             f"with prediction {prediction}."})]),
            Turn("", [("RecoveryPlan", plan)]),
        ],
        "impact": [
            Turn("", [("predict_resolution_time", {"shipment_id": S1})]),
            Turn("", [("calculate_supply_risk", risk),
                      ("calculate_supply_risk", {**risk, "priority_level": "critical_high"}),
                      ("calculate_supply_risk", {**risk, "priority_level": "critical"})]),
            Turn(f"{prediction} is longer. {high}: critical and high orders are short. {critical}: critical only is covered."),
        ],
        "action": [
            Turn("", [("validate_action", {**risk, "source_plant": "1200", "quantity_t": 10})]),
            Turn(f"{blocked} rejected: plant 1200 is at its safety stock; no further transfer is feasible."),
        ],
    }


def s2_event(store: JsonStore) -> dict[str, list[Turn]]:
    """S2 congestion: start from inventory exposure and keep the plan."""
    prediction, current = records.next_id(store, "prediction"), records.next_id(store, "assessment")
    plan = _plan(
        case_id=_case(store, S2)["case_id"],
        exception="Yard congestion at Tanjung Priok delays discharge; the documents are not in question.",
        evidence=[{"fact": "Yard congestion at Tanjung Priok delays discharge of SHP-1002.", "source": "event feed"}],
        prediction_id=prediction,
        current_plan_assessment_id=current,
        recommendation="Keep the current plan: stock at plant 1100 covers the predicted delay.",
        next_check="Discharge progress at Tanjung Priok.",
    )
    return {
        "orchestrator": [
            Turn("A congestion event: start from inventory exposure.",
                 [("impact_agent", {"input": f"Predict the resolution time for {S2} and assess the current plan: "
                                             "all orders, no transfer."})]),
            Turn("", [("RecoveryPlan", plan)]),
        ],
        "impact": [
            Turn("", [("predict_resolution_time", {"shipment_id": S2})]),
            Turn("", [("calculate_supply_risk", {"shipment_id": S2, "prediction_id": prediction})]),
            Turn(f"{prediction} gives the resolution time. {current}: the current plan is covered."),
        ],
    }


SCRIPTS = {"S1-DOC-HOLD": s1_event, "S1-ETA-SLIP": s1_eta_slip, "S2-CONGESTION": s2_event}
