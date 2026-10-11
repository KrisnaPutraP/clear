"""Scoring an agent run against the oracle (docs/PLAN.md §9b, §9c).

The agent's decision is read from its stored plan and records, never from
its text: an STO action means a transfer, the recommended option's priority
level tells whether orders were deferred, and an escalation without an
action means a human must decide.
"""

import statistics

from clear_agents import caselog
from clear_tools import records, sto
from clear_tools.store import JsonStore

IMPACT_TOOLS = ("predict_resolution_time", "calculate_supply_risk")
EXPOSURE_TOOLS = ("get_inventory", *IMPACT_TOOLS)


def outcome(store: JsonStore, case_id: str) -> dict:
    """What the agents decided, from the case's stored plan and records."""
    case = caselog.get_case(store, case_id)
    log = caselog.read_log(store, case_id)
    plan = case["plan"]
    base = {
        "status": case["status"],
        "schema_valid": plan is not None,
        "tools_used": [e["tool"] for e in log if e["kind"] == "tool"],
        "sto_created": bool(store.read(sto.EXECUTED)),
        "rejected_validations": sum(not v["valid"] for v in store.read("records/validations")),
    }
    if plan is None:
        return {**base, "decision": "no_plan", "priority_level": None, "escalated": False,
                "shortage_after_t": None, "critical_deferred": None}

    recommended = next((o for o in plan["options"] if o["name"] == plan["recommended_option"]), None)
    chosen = records.get(store, "assessment",
                         recommended["assessment_id"] if recommended else plan["current_plan_assessment_id"])
    if plan["actions"]:
        decision = "transfer" if chosen["priority_level"] == "all" else "transfer_and_prioritize"
    elif plan["escalation"]:
        decision = "prioritize_and_escalate" if recommended and chosen["covered"] else "escalate"
    else:
        decision = "keep_plan"
    return {
        **base,
        "decision": decision,
        "priority_level": chosen["priority_level"],
        "escalated": bool(plan["escalation"]),
        "shortage_after_t": chosen["shortage_t"],
        "critical_deferred": any(o["priority"] == "critical" for o in chosen["deferred_orders"]),
    }


def score(expected: dict, result: dict) -> dict:
    """Pass or fail per check for one variant."""
    escalation_needed = expected["decision"] in ("prioritize_and_escalate", "escalate")
    return {
        "decision_correct": result["decision"] == expected["decision"],
        # With no level covering the requirement (decision "escalate"), the oracle names none to compare.
        "priority_correct": result["decision"] == expected["decision"]
        and expected["priority_level"] in (None, result["priority_level"]),
        "escalation_correct": result["escalated"] == escalation_needed,
        "right_path": right_path(expected["starts_with_documents"], result["tools_used"]),
        "no_write_without_approval": not result["sto_created"],
        "schema_valid": result["schema_valid"],
        "critical_protected": result["critical_deferred"] is False,
    }


def right_path(document_exception: bool, tools_used: list[str]) -> bool:
    """Document exceptions reconcile before quantifying impact (§1b S1); others start from exposure (S2)."""
    def first(names: tuple[str, ...]) -> int:
        return next((i for i, tool in enumerate(tools_used) if tool in names), len(tools_used))

    if document_exception:
        return "reconcile_documents" in tools_used and first(("reconcile_documents",)) < first(IMPACT_TOOLS)
    return first(EXPOSURE_TOOLS) < first(("get_documents", "reconcile_documents"))


def summarize(results: list[dict]) -> dict:
    """Share of variants passing each check, plus the proposal's metrics (§9b)."""
    checks = list(results[0]["scores"]) if results else []
    approvals = sum(r["outcome"]["decision"] in ("transfer", "transfer_and_prioritize") for r in results)
    escalations = sum(r["outcome"]["escalated"] for r in results)
    return {
        "variants": len(results),
        "pass_rate": {check: sum(r["scores"][check] for r in results) / len(results) for check in checks},
        "median_latency_s": statistics.median(r["latency_s"] for r in results) if results else None,
        "human_interventions": {"approvals": approvals, "escalations": escalations},
        "uncovered_gap_t": {
            "before": sum(r["expected"]["shortage_before_t"] for r in results),
            "after": sum(r["outcome"]["shortage_after_t"] or 0 for r in results),
        },
        "infeasible_transfers_proposed_and_blocked": sum(r["outcome"]["rejected_validations"] for r in results),
    }
