"""A scripted stand-in for the Bedrock model, for tests and the UI example only.

ScriptedModel replays fixed turns (text and tool calls) in the Bedrock
stream format, so the real Strands agents, tools, hooks, and case log run
end to end without AWS. It decides nothing and must never stand in for the
model in the demo. The S1 and S2 scripts reproduce the expected agent steps
on a freshly reset store, where record IDs are predictable.
"""

import itertools
import json
import re
from dataclasses import dataclass, field

from strands.models.model import Model

from clear_tools import read
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
    """A model factory that gives each role its scripted turns."""
    return lambda role: ScriptedModel(script.get(role, []))


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


def _plan(**fields) -> dict:
    return {"options": [], "recommended_option": None, "actions": [], "escalation": None, **fields}


def s1_event(store: JsonStore) -> dict[str, list[Turn]]:
    """S1 exception: reconcile, quantify, rejected transfer, re-plan, validated STO awaiting approval."""
    extractions = extract_fields(read.get_documents(store, S1))
    risk = {"shipment_id": S1, "prediction_id": "PRED-0001"}
    transfer = {**risk, "transfer_quantity_t": 100, "source_plant": "1200"}
    options = [
        {"name": "Transfer 100 t from 1200", "assessment_id": "ASM-0002",
         "note": "The feasible transfer alone still leaves a shortage."},
        {"name": "Transfer 100 t from 1200 + critical and high orders", "assessment_id": "ASM-0003",
         "validation_id": "VAL-0002", "note": "Covers the requirement; normal-priority orders wait."},
    ]
    plan = _plan(
        case_id="CASE-0001",
        exception="Customs document hold: the packing list states a lower quantity than the invoice and PO.",
        evidence=[{"fact": "Packing list quantity differs from the invoice and the purchase order.",
                   "source": "reconcile_documents"},
                  {"fact": "Plant 1200 holds the material above its safety stock.", "source": "get_inventory"}],
        prediction_id="PRED-0001",
        current_plan_assessment_id="ASM-0001",
        options=options,
        recommendation="Transfer the feasible quantity from plant 1200 and serve critical and high orders "
                       "until the shipment clears; the full transfer was rejected by the safety-stock rule.",
        recommended_option=options[1]["name"],
        actions=[{"validation_id": "VAL-0002", "status": "awaiting_approval"}],
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
                 [("action_agent", {"input": f"Validate an STO of 160 t from plant 1200 for {S1} "
                                             "with prediction PRED-0001."})]),
            Turn("Rejected by the safety-stock rule. Assess the feasible quantity, alone and with priorities.",
                 [("impact_agent", {"input": f"With PRED-0001 for {S1}, assess a 100 t transfer from plant 1200 "
                                             "serving all orders, and the same transfer serving critical_high orders."})]),
            Turn("The feasible transfer plus critical and high orders is covered. Validate it.",
                 [("action_agent", {"input": f"Validate an STO of 100 t from plant 1200 for {S1} "
                                             "with prediction PRED-0001."})]),
            Turn("", [("RecoveryPlan", plan)]),
        ],
        "evidence": [
            Turn("", [("get_shipment", {"shipment_id": S1}), ("get_purchase_order", {"purchase_order": "4500001021"}),
                      ("get_inventory", {"material": "CHEM-BX40"}), ("get_documents", {"shipment_id": S1})]),
            Turn("", [("reconcile_documents", {"shipment_id": S1, "extractions": extractions})]),
            Turn("- The packing list quantity differs from the invoice and the PO (reconcile_documents).\n"
                 "- Plant 1200 holds CHEM-BX40 above its safety stock (get_inventory)."),
        ],
        "impact": [
            Turn("", [("predict_resolution_time", {"shipment_id": S1})]),
            Turn("", [("calculate_supply_risk", risk)]),
            Turn("PRED-0001 (baseline-median). ASM-0001: the current plan leaves a shortage."),
            Turn("", [("calculate_supply_risk", transfer),
                      ("calculate_supply_risk", {**transfer, "priority_level": "critical_high"})]),
            Turn("ASM-0002: the transfer alone is short. ASM-0003: with critical and high orders it is covered."),
        ],
        "action": [
            Turn("", [("validate_action", {**risk, "source_plant": "1200", "quantity_t": 160})]),
            Turn("VAL-0001 rejected: plant 1200 would fall below its safety stock."),
            Turn("", [("validate_action", {**risk, "source_plant": "1200", "quantity_t": 100})]),
            Turn("VAL-0002 is valid."),
        ],
    }


def s1_approval(store: JsonStore) -> dict[str, list[Turn]]:
    """After APR-0001 for VAL-0002: create the STO, verify stock, mark the action executed."""
    plan = s1_event(store)["orchestrator"][-1].tool_calls[0][1]
    executed = {**plan, "actions": [{"validation_id": "VAL-0002", "status": "executed", "purchase_order": "4500001023"}],
                "next_check": "Arrival of the transfer at plant 1100, and the customs response."}
    return {
        "orchestrator": [
            Turn("Approved: create the STO and verify stock.",
                 [("action_agent", {"input": "Create the STO for VAL-0002 with approval APR-0001, "
                                             "then verify stock positions for CHEM-BX40."})]),
            Turn("", [("RecoveryPlan", executed)]),
        ],
        "action": [
            Turn("", [("create_stock_transport_order", {"validation_id": "VAL-0002", "approval_id": "APR-0001"})]),
            Turn("", [("get_inventory", {"material": "CHEM-BX40"})]),
            Turn("STO 4500001023 created; plant 1200 is at its safety stock and plant 1100 has the transfer in transit."),
        ],
    }


def s2_event(store: JsonStore) -> dict[str, list[Turn]]:
    """S2 congestion: start from inventory exposure and keep the plan."""
    plan = _plan(
        case_id="CASE-0001",
        exception="Yard congestion at Tanjung Priok delays discharge; the documents are not in question.",
        evidence=[{"fact": "Yard congestion at Tanjung Priok delays discharge of SHP-1002.", "source": "event feed"}],
        prediction_id="PRED-0001",
        current_plan_assessment_id="ASM-0001",
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
            Turn("", [("calculate_supply_risk", {"shipment_id": S2, "prediction_id": "PRED-0001"})]),
            Turn("PRED-0001 (baseline-median). ASM-0001: the current plan is covered."),
        ],
    }
