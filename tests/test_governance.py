"""The governed write path (docs/PLAN.md §5a, §6): an STO needs a passing
validation and a human approval of that same validation, and runs once."""

import pytest

from clear_tools.approvals import record_approval
from clear_tools.events import prepared_event, record_event
from clear_tools.predict import predict_resolution_time
from clear_tools.sto import create_stock_transport_order
from clear_tools.validate import validate_action

SHIPMENT = "SHP-1001"


@pytest.fixture
def validate(store):
    """validate_action for the S1 case after its document exception."""
    record_event(store, prepared_event(store, "S1-DOC-HOLD"))
    prediction_id = predict_resolution_time(store, SHIPMENT)["prediction_id"]
    return lambda quantity: validate_action(store, SHIPMENT, prediction_id, "1200", quantity)


def approve(store, validation):
    return record_approval(store, validation["validation_id"], "Demo Planner", "approved")


def test_approval_cannot_be_reused_for_another_validation(store, validate):
    approved = validate(10)
    other = validate(8)
    approval = approve(store, approved)

    with pytest.raises(PermissionError):
        create_stock_transport_order(store, other["validation_id"], approval["approval_id"])


def test_rejected_validation_cannot_become_an_sto(store, validate):
    validation = validate(10)
    rejection = record_approval(store, validation["validation_id"], "Demo Planner", "rejected",
                                reason="Prefer emergency sourcing")

    with pytest.raises(PermissionError):
        create_stock_transport_order(store, validation["validation_id"], rejection["approval_id"])


def test_failed_validation_cannot_be_approved(store, validate):
    failed = validate(100)

    assert not failed["valid"]
    with pytest.raises(PermissionError):
        approve(store, failed)


def test_rejection_needs_a_reason(store, validate):
    with pytest.raises(ValueError):
        record_approval(store, validate(10)["validation_id"], "Demo Planner", "rejected")


def test_validation_executes_only_once(store, validate):
    validation = validate(10)
    approval = approve(store, validation)
    create_stock_transport_order(store, validation["validation_id"], approval["approval_id"])

    with pytest.raises(PermissionError):
        create_stock_transport_order(store, validation["validation_id"], approval["approval_id"])


def test_sto_is_blocked_when_stock_changed_since_validation(store, validate):
    first, second = validate(20), validate(20)  # Each fits alone, not both.
    first_approval, second_approval = approve(store, first), approve(store, second)
    create_stock_transport_order(store, first["validation_id"], first_approval["approval_id"])

    with pytest.raises(PermissionError):
        create_stock_transport_order(store, second["validation_id"], second_approval["approval_id"])


def test_unknown_ids_are_rejected(store, validate):
    validation = validate(10)

    with pytest.raises(LookupError):
        create_stock_transport_order(store, validation["validation_id"], "APR-9999")
