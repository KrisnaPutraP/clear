"""Scenario S1 (hero) invariants (docs/PLAN.md §1b, §4c, §5c).

These tests guard the demo story, not exact numbers: whenever seed data or
tool logic changes, S1 must still unfold in this order. Quantities and
thresholds come from the tools, computed on data/seed/.
"""

import pytest

pytestmark = pytest.mark.skip(reason="not implemented yet (MVP item 1)")


def test_documents_contain_exactly_one_discrepancy():
    """reconcile_documents finds exactly one clear discrepancy (§4b)."""
    raise NotImplementedError


def test_initial_coverage_is_below_requirement():
    """With all orders served, coverage is below predicted resolution plus
    port-to-plant transit, so there is a shortage."""
    raise NotImplementedError


def test_full_shortage_transfer_is_rejected_by_source_safety_stock():
    """validate_action rejects transferring the whole shortage because the
    source plant would fall below safety stock, and returns the maximum
    feasible quantity."""
    raise NotImplementedError


def test_partial_transfer_with_critical_and_high_orders_meets_requirement():
    """A transfer within the feasible maximum, serving only critical and high
    orders, meets the requirement."""
    raise NotImplementedError


def test_sto_writes_exactly_the_validated_quantity():
    """create_stock_transport_order writes the quantity of the referenced
    validation, nothing else."""
    raise NotImplementedError


def test_eta_slip_limits_service_to_critical_orders():
    """After the ETA slip, critical and high orders no longer fit the new
    requirement; critical-only does, and the remaining orders are deferred."""
    raise NotImplementedError
