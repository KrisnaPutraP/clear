"""Scenario S1 (hero) invariants (docs/PLAN.md §1b, §4c, §5c).

These tests guard the demo story, not exact numbers: whenever seed data or
tool logic changes, S1 must still unfold in this order. Quantities and
thresholds come from the tools, computed on data/seed/.
"""

import pytest

from clear_tools.approvals import record_approval
from clear_tools.events import prepared_event, record_event
from clear_tools.predict import predict_resolution_time
from clear_tools.read import get_documents, get_inventory
from clear_tools.reconcile import reconcile_documents
from clear_tools.sto import create_stock_transport_order
from clear_tools.supply_risk import calculate_supply_risk
from clear_tools.validate import validate_action

SHIPMENT = "SHP-1001"
MATERIAL = "CHEM-BX40"
PLANT = "1100"
SOURCE = "1200"


@pytest.fixture
def prediction(store):
    """State after the document exception: event recorded, resolution predicted."""
    record_event(store, prepared_event(store, "S1-DOC-HOLD"))
    return predict_resolution_time(store, SHIPMENT)


def shortage_and_max_transfer(store, prediction):
    shortage = calculate_supply_risk(store, SHIPMENT, prediction["prediction_id"])["shortage_t"]
    rejected = validate_action(store, SHIPMENT, prediction["prediction_id"], SOURCE, shortage)
    return shortage, rejected


def execute_partial_transfer(store, prediction):
    _, rejected = shortage_and_max_transfer(store, prediction)
    validation = validate_action(
        store, SHIPMENT, prediction["prediction_id"], SOURCE, rejected["max_feasible_quantity"]
    )
    approval = record_approval(store, validation["validation_id"], "Demo Planner", "approved")
    return validation, create_stock_transport_order(store, validation["validation_id"], approval["approval_id"])


def test_documents_contain_exactly_one_discrepancy(store, extract):
    """reconcile_documents finds exactly one clear discrepancy (§4b): quantity."""
    result = reconcile_documents(store, SHIPMENT, extract(get_documents(store, SHIPMENT)))

    assert result["missing_documents"] == []
    assert result["unverified_extractions"] == []
    assert result["not_extracted"] == []
    assert [d["field"] for d in result["discrepancies"]] == ["quantity"]
    assert result["discrepancies"][0]["mismatched_documents"] == ["packing_list"]


def test_initial_coverage_is_below_requirement(store, prediction):
    """With all orders served, coverage is below predicted resolution plus
    port-to-plant transit, so there is a shortage."""
    risk = calculate_supply_risk(store, SHIPMENT, prediction["prediction_id"])

    assert prediction["source"] == "baseline-median"
    assert risk["coverage_days"] < risk["required_coverage_days"]
    assert risk["shortage_t"] > 0


def test_full_shortage_transfer_is_rejected_by_source_safety_stock(store, prediction):
    """validate_action rejects transferring the whole shortage because the
    source plant would fall below safety stock, and returns the maximum
    feasible quantity."""
    shortage, rejected = shortage_and_max_transfer(store, prediction)

    assert not rejected["valid"]
    assert [v["rule"] for v in rejected["violations"]] == ["source_safety_stock"]
    assert 0 < rejected["max_feasible_quantity"] < shortage


def test_partial_transfer_with_critical_and_high_orders_meets_requirement(store, prediction):
    """A transfer within the feasible maximum is not enough on its own, but
    serving only critical and high orders meets the requirement."""
    _, rejected = shortage_and_max_transfer(store, prediction)
    plan = {"transfer_quantity": rejected["max_feasible_quantity"], "source_plant": SOURCE}

    all_orders = calculate_supply_risk(store, SHIPMENT, prediction["prediction_id"], "all", **plan)
    prioritized = calculate_supply_risk(store, SHIPMENT, prediction["prediction_id"], "critical_high", **plan)

    assert not all_orders["covered"]
    assert prioritized["covered"]


def test_sto_writes_exactly_the_validated_quantity(store, prediction):
    """create_stock_transport_order writes the quantity of the referenced
    validation, and stock positions move by exactly that amount."""
    before = {p["plant"]: p for p in get_inventory(store, MATERIAL)["plants"]}
    validation, sto = execute_partial_transfer(store, prediction)
    after = {p["plant"]: p for p in get_inventory(store, MATERIAL)["plants"]}

    assert sto["quantity_t"] == validation["quantity"]
    assert after[SOURCE]["unrestricted_t"] == before[SOURCE]["unrestricted_t"] - sto["quantity_t"]
    assert after[SOURCE]["unrestricted_t"] >= after[SOURCE]["safety_stock_t"]
    assert after[PLANT]["in_transit_t"] == sto["quantity_t"]


def test_eta_slip_limits_service_to_critical_orders(store, prediction):
    """After the ETA slip, critical and high orders no longer fit the new
    requirement; critical-only does, the remaining orders are deferred, and
    no further transfer is feasible (emergency sourcing goes to a human)."""
    execute_partial_transfer(store, prediction)
    record_event(store, prepared_event(store, "S1-ETA-SLIP"))
    slipped = predict_resolution_time(store, SHIPMENT)

    critical_high = calculate_supply_risk(store, SHIPMENT, slipped["prediction_id"], "critical_high")
    critical = calculate_supply_risk(store, SHIPMENT, slipped["prediction_id"], "critical")
    another_transfer = validate_action(store, SHIPMENT, slipped["prediction_id"], SOURCE, 1)

    assert slipped["predicted_days"] > prediction["predicted_days"]
    assert not critical_high["covered"]
    assert critical["covered"]
    assert {o["priority"] for o in critical["deferred_orders"]} == {"high", "normal"}
    assert another_transfer["max_feasible_quantity"] == 0
