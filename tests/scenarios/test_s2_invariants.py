"""Scenario S2 (contrast) invariants (docs/PLAN.md §1b, §4c, §5c).

S2 is port congestion without a document problem. Coverage is sufficient, so
the right outcome is to keep the current plan.
"""

import pytest

pytestmark = pytest.mark.skip(reason="not implemented yet (MVP item 1)")


def test_documents_have_no_discrepancy():
    """reconcile_documents finds no discrepancy and no missing document."""
    raise NotImplementedError


def test_coverage_meets_requirement_so_plan_is_kept():
    """With all orders served, coverage already meets the requirement, so no
    transfer is needed."""
    raise NotImplementedError
