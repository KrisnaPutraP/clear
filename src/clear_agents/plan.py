"""Recovery plan schema (docs/PLAN.md §5d) and its checks.

The orchestrator returns a RecoveryPlan as structured output. The plan cites
numbers by the IDs of the tool results that hold them (prediction_id,
assessment_id, validation_id) instead of typing them, so the LLM cannot
mistype a business number. check() rejects IDs that do not exist or belong
to another shipment, and a plan that defers orders or leaves a shortage
without a transfer and without telling a human (§6d). render() fills in the
numbers from the stored records for the approval card and the UI.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from clear_tools import read, records, sto
from clear_tools.store import JsonStore


_NO_ESCALATION = re.compile(r"\s*(?:none|null|n/?a)?\s*(?:$|[-–—:.,;(])", re.IGNORECASE)


class Evidence(BaseModel):
    fact: str = Field(description="One fact in a short sentence.")
    source: str = Field(description="Tool or document the fact comes from, e.g. reconcile_documents.")


class Option(BaseModel):
    name: str = Field(description="Short name, e.g. 'Transfer from 1200 + critical and high orders'.")
    assessment_id: str = Field(description="ID from calculate_supply_risk for exactly this option.")
    validation_id: str | None = Field(default=None, description="ID from validate_action if the option has a transfer.")
    note: str = Field(description="Why the option is or is not acceptable, in one sentence.")


class Action(BaseModel):
    validation_id: str = Field(description="ID from validate_action of the STO.")
    status: Literal["awaiting_approval", "executed"]
    purchase_order: str | None = Field(default=None, description="STO number, once created.")


class RecoveryPlan(BaseModel):
    """Recovery plan for one shipment exception. Cite every number by the ID of the tool
    result that holds it (prediction_id, assessment_id, validation_id); never type numbers."""

    case_id: str
    exception: str = Field(description="Exception type and its cause according to the evidence.")
    evidence: list[Evidence]
    prediction_id: str = Field(description="ID from predict_resolution_time.")
    current_plan_assessment_id: str = Field(
        description="ID from calculate_supply_risk for the current plan: all orders, no transfer."
    )
    options: list[Option] = Field(default_factory=list, description="Options impact_agent assessed, beyond the current plan.")
    recommendation: str = Field(description="Chosen course of action and why, in at most two sentences.")
    recommended_option: str | None = Field(
        default=None,
        description="Name of the chosen option, one of options; None when the current plan is kept or no option "
                    "covers the requirement.",
    )
    actions: list[Action] = Field(default_factory=list, description="STOs, only for validated transfers.")
    escalation: str | None = Field(
        default=None,
        description="A decision only a human can make: emergency sourcing when the validator allows no transfer "
                    "at all and orders are deferred, or when no option covers the requirement. Otherwise leave it "
                    "empty (null): do not write None or an explanation here. Orders deferred behind a feasible "
                    "transfer need no escalation. Contingencies and customs follow-up go in next_check.",
    )
    next_check: str = Field(description="What to monitor next.")

    @field_validator("escalation")
    @classmethod
    def _no_escalation_as_text(cls, value: str | None) -> str | None:
        """A model sometimes writes "None - no escalation needed" instead of null; that is no escalation."""
        return None if value is None or _NO_ESCALATION.match(value) else value


def check(store: JsonStore, plan: RecoveryPlan, shipment_id: str) -> list[str]:
    """Problems with a plan; an empty list means it can be shown and acted on."""
    return check_references(store, plan, shipment_id) or check_escalation(store, plan)


def check_escalation(store: JsonStore, plan: RecoveryPlan) -> list[str]:
    """Without a transfer, a course that defers orders or leaves a shortage needs a human decision (§6d)."""
    if plan.actions or plan.escalation:
        return []
    recommended = next((o for o in plan.options if o.name == plan.recommended_option), None)
    chosen = records.get(store, "assessment",
                         recommended.assessment_id if recommended else plan.current_plan_assessment_id)
    if chosen["covered"] and chosen["priority_level"] == "all":
        return []
    return [f"{chosen['assessment_id']} defers orders or leaves a shortage and the plan has no transfer action: add "
            "the validated transfer, or state in escalation what a human must decide (emergency sourcing)"]


def check_references(store: JsonStore, plan: RecoveryPlan, shipment_id: str) -> list[str]:
    """Problems with the IDs a plan cites; an empty list means every reference holds."""
    problems: list[str] = []

    def lookup(kind: str, record_id: str | None) -> dict | None:
        if not record_id:
            return None
        try:
            record = records.get(store, kind, record_id)
        except LookupError:
            problems.append(f"{record_id} does not exist")
            return None
        if record["shipment_id"] != shipment_id:
            problems.append(f"{record_id} belongs to {record['shipment_id']}, not {shipment_id}")
            return None
        return record

    lookup("prediction", plan.prediction_id)
    current = lookup("assessment", plan.current_plan_assessment_id)
    if current and (current["priority_level"] != "all" or current["transfer"]):
        problems.append(f"{plan.current_plan_assessment_id} is not the current plan (all orders, no transfer)")
    for option in plan.options:
        lookup("assessment", option.assessment_id)
        lookup("validation", option.validation_id)
    if plan.recommended_option and plan.recommended_option not in {o.name for o in plan.options}:
        problems.append(f"recommended_option {plan.recommended_option!r} is not one of the options")

    executed = {r["validation_id"]: r for r in store.read(sto.EXECUTED)}
    for action in plan.actions:
        validation = lookup("validation", action.validation_id)
        if not validation:
            continue
        if not validation["valid"]:
            problems.append(f"{action.validation_id} failed validation and cannot be an action")
        sto_record = executed.get(action.validation_id)
        if action.status == "executed" and (not sto_record or sto_record["purchase_order"] != action.purchase_order):
            problems.append(f"{action.validation_id} has no executed STO {action.purchase_order}")
        if action.status == "awaiting_approval" and sto_record:
            problems.append(f"{action.validation_id} was already executed as STO {sto_record['purchase_order']}")
    return problems


def render(store: JsonStore, plan: RecoveryPlan) -> dict:
    """The plan with every cited number filled in from the stored records."""
    prediction = records.get(store, "prediction", plan.prediction_id)
    current = records.get(store, "assessment", plan.current_plan_assessment_id)
    approvals = store.read("records/approvals")
    executed = {r["validation_id"]: r for r in store.read(sto.EXECUTED)}

    def assessment_numbers(record: dict) -> dict:
        keys = ("assessment_id", "priority_level", "coverage_days", "required_coverage_days",
                "covered", "shortage_t", "transfer", "deferred_orders", "sources")
        return {k: record[k] for k in keys}

    def validation_numbers(validation_id: str | None) -> dict | None:
        if not validation_id:
            return None
        record = records.get(store, "validation", validation_id)
        keys = ("validation_id", "valid", "quantity", "source_plant", "destination_plant",
                "violations", "max_feasible_quantity")
        return {k: record[k] for k in keys}

    actions = []
    for action in plan.actions:
        approval = next((a for a in approvals if a["validation_id"] == action.validation_id), None)
        actions.append({
            **action.model_dump(),
            "validation": validation_numbers(action.validation_id),
            "approval": approval,
            "sto": executed.get(action.validation_id),
        })

    verification = None
    if any(action.status == "executed" for action in plan.actions):
        verification = read.get_inventory(store, current["material"])

    return {
        "case_id": plan.case_id,
        "exception": plan.exception,
        "evidence": [e.model_dump() for e in plan.evidence],
        "impact": {
            "prediction": {k: prediction[k] for k in ("prediction_id", "predicted_days", "source", "basis")},
            **assessment_numbers(current),
        },
        "options": [
            {**o.model_dump(), "assessment": assessment_numbers(records.get(store, "assessment", o.assessment_id)),
             "validation": validation_numbers(o.validation_id)}
            for o in plan.options
        ],
        "recommendation": plan.recommendation,
        "recommended_option": plan.recommended_option,
        "actions": actions,
        "verification": verification,
        "escalation": plan.escalation,
        "next_check": plan.next_check,
    }
