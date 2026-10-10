"""Agents, case log, and UI contract end to end, with a scripted model in place
of Bedrock (docs/PLAN.md §2a, §5d, §6c, §7b-d). The model is scripted; the
agents, tools, hooks, plan checks, and case log are the real ones."""

from clear_agents import runner
from clear_agents.plan import RecoveryPlan, check_references
from clear_agents.testing import ScriptedModel, s1_approval, s1_event, s2_event, scripted
from clear_app.contract import Clear


def test_only_the_action_agent_can_write(store):
    agents = runner.build_agents(store, "CASE-0001", lambda role: ScriptedModel([]))

    assert sorted(agents.orchestrator.tool_names) == ["action_agent", "evidence_agent", "impact_agent"]
    assert "create_stock_transport_order" in agents.action.tool_names
    for reader in (agents.evidence, agents.impact):
        assert "create_stock_transport_order" not in reader.tool_names
        assert "validate_action" not in reader.tool_names


def test_s1_stops_for_approval_then_executes_the_approved_sto(store):
    clear = Clear(store, scripted(s1_event(store)))
    case_id = clear.send_event("S1-DOC-HOLD", wait=True)
    case = clear.get_case(case_id)
    log = clear.get_case_log(case_id)

    assert case["status"] == "awaiting_approval"
    assert [e["tool"] for e in log if e.get("flag") == "rejected"] == ["validate_action"]
    assert [e["tool"] for e in log if e.get("flag") == "discrepancy"] == ["reconcile_documents"]
    [action] = case["plan"]["actions"]
    assert action["validation"]["quantity"] == 100  # Filled in from VAL-0002, not typed by the model.
    assert case["plan"]["impact"]["prediction"]["source"] == "baseline-median"

    clear.model_for = scripted(s1_approval(store))
    clear.submit_decision(case_id, "VAL-0002", "Demo Planner", "approved", wait=True)
    case = clear.get_case(case_id)

    assert case["status"] == "monitoring"
    [action] = case["plan"]["actions"]
    assert action["sto"]["purchase_order"] == "4500001023"
    plants = {p["plant"]: p for p in case["plan"]["verification"]["plants"]}
    assert plants["1200"]["unrestricted_t"] == plants["1200"]["safety_stock_t"]
    assert plants["1100"]["in_transit_t"] == 100


def test_s2_keeps_the_plan(store):
    clear = Clear(store, scripted(s2_event(store)))
    case = clear.get_case(clear.send_event("S2-CONGESTION", wait=True))

    assert case["status"] == "monitoring"
    assert case["plan"]["actions"] == []
    assert case["plan"]["impact"]["covered"]


def test_rejection_moves_the_case_to_a_human_decision(store):
    clear = Clear(store, scripted(s1_event(store)))
    case_id = clear.send_event("S1-DOC-HOLD", wait=True)

    clear.submit_decision(case_id, "VAL-0002", "Demo Planner", "rejected", reason="Prefer emergency sourcing")

    case = clear.get_case(case_id)
    assert case["status"] == "needs_human_decision"
    assert "Prefer emergency sourcing" in case["status_reason"]


def test_plan_citing_unknown_ids_is_rejected(store):
    plan = RecoveryPlan(case_id="CASE-0001", exception="x", evidence=[], prediction_id="PRED-0042",
                        current_plan_assessment_id="ASM-0042", recommendation="x", next_check="x",
                        actions=[{"validation_id": "VAL-0042", "status": "awaiting_approval"}])

    assert check_references(store, plan, "SHP-1001") == [
        "PRED-0042 does not exist", "ASM-0042 does not exist", "VAL-0042 does not exist",
    ]


def test_failed_run_leaves_a_readable_case(store, monkeypatch):
    monkeypatch.delenv("CLEAR_BEDROCK_MODEL_ID", raising=False)
    clear = Clear(store)  # Real Bedrock factory without a model ID.

    case = clear.get_case(clear.send_event("S2-CONGESTION", wait=True))

    assert case["status"] == "needs_human_decision"
    assert "CLEAR_BEDROCK_MODEL_ID" in case["status_reason"]
