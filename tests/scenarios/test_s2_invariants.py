"""Scenario S2 (contrast) invariants (docs/PLAN.md §1b, §4c, §5c).

S2 is port congestion without a document problem. Coverage is sufficient, so
the right outcome is to keep the current plan.
"""

from clear_tools.events import prepared_event, record_event
from clear_tools.predict import predict_resolution_time
from clear_tools.read import get_documents
from clear_tools.reconcile import reconcile_documents
from clear_tools.supply_risk import calculate_supply_risk

SHIPMENT = "SHP-1002"


def test_documents_have_no_discrepancy(store, extract):
    """reconcile_documents finds no discrepancy and no missing document."""
    result = reconcile_documents(store, SHIPMENT, extract(get_documents(store, SHIPMENT)))

    assert result["consistent"]
    assert result["discrepancies"] == []
    assert result["missing_documents"] == []


def test_coverage_meets_requirement_so_plan_is_kept(store):
    """With all orders served, coverage already meets the requirement, so no
    transfer is needed."""
    record_event(store, prepared_event(store, "S2-CONGESTION"))
    prediction = predict_resolution_time(store, SHIPMENT)
    risk = calculate_supply_risk(store, SHIPMENT, prediction["prediction_id"])

    assert risk["covered"]
    assert risk["shortage_t"] == 0
    assert risk["deferred_orders"] == []
