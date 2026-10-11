"""The evaluation harness (docs/PLAN.md §9b, §9c): oracle ground truth for every
variant, and the scoring path end to end with the scripted model."""

import pytest

from clear_agents.testing import ScriptedDirector
from clear_eval import harness, oracle, scoring, variants

EXPECTED = {
    "A1": ("transfer_and_prioritize", "critical_high"), "A2": ("transfer_and_prioritize", "critical_high"),
    "A3": ("transfer_and_prioritize", "critical_high"), "A4": ("transfer_and_prioritize", "critical"),
    "B1": ("transfer", "all"), "B2": ("transfer", "all"), "B3": ("transfer", "all"),
    "C1": ("escalate", None), "C2": ("prioritize_and_escalate", "critical"),
    "C3": ("prioritize_and_escalate", "critical_high"), "C4": ("prioritize_and_escalate", "critical"),
    "D1": ("keep_plan", "all"), "D2": ("keep_plan", "all"), "D3": ("keep_plan", "all"),
    "E1": ("keep_plan", "all"), "E2": ("keep_plan", "all"), "E3": ("keep_plan", "all"),
    "F1": ("transfer", "all"), "F2": ("transfer_and_prioritize", "critical_high"), "F3": ("escalate", None),
}


@pytest.mark.parametrize("spec", variants.VARIANTS, ids=lambda spec: spec["id"])
def test_oracle_decision(spec, tmp_path):
    store = variants.build_store(spec, tmp_path / spec["id"])

    result = oracle.expected(store, spec["event_id"])

    assert (result["decision"], result["priority_level"]) == EXPECTED[spec["id"]]


def test_oracle_leaves_the_run_store_untouched(tmp_path):
    store = variants.build_store(variants.variant("A1"), tmp_path / "A1")

    oracle.expected(store, "S1-DOC-HOLD")

    assert store.read("records/predictions") == []
    assert store.read("logistics/shipments")[0]["exception"] is None


def test_scripted_runs_pass_every_check(tmp_path):
    seen = []
    report = harness.run_batch([variants.variant("A1"), variants.variant("E1")], ScriptedDirector, tmp_path,
                               on_result=seen.append)

    assert seen == report["results"]
    for result in report["results"]:
        assert all(result["scores"].values()), (result["variant"], result["scores"])
    summary = report["summary"]
    assert summary["uncovered_gap_t"] == {"before": 32, "after": 0}
    assert summary["human_interventions"] == {"approvals": 1, "escalations": 0}
    assert summary["infeasible_transfers_proposed_and_blocked"] == 1


@pytest.mark.parametrize("document_exception, tools, ok", [
    (True, ["get_inventory", "get_documents", "reconcile_documents", "predict_resolution_time"], True),
    (True, ["predict_resolution_time", "reconcile_documents"], False),
    (True, ["predict_resolution_time", "calculate_supply_risk"], False),
    (False, ["predict_resolution_time", "calculate_supply_risk"], True),
    (False, ["reconcile_documents", "get_inventory"], False),
])
def test_right_path(document_exception, tools, ok):
    assert scoring.right_path(document_exception, tools) is ok


def test_escalation_with_no_covering_level_scores_without_a_priority():
    result = {"decision": "escalate", "priority_level": "critical_high", "escalated": True, "sto_created": False,
              "tools_used": ["get_inventory", "predict_resolution_time"], "schema_valid": True,
              "critical_deferred": False}

    assert scoring.score({"decision": "escalate", "priority_level": None, "starts_with_documents": False},
                         result)["priority_correct"]
    assert not scoring.score({"decision": "prioritize_and_escalate", "priority_level": "critical",
                              "starts_with_documents": False}, result)["priority_correct"]
