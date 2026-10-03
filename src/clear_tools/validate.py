"""validate_action (docs/PLAN.md §5c).

Deterministic. Checks a proposed STO against the business rules:
1. Source plant stock after the transfer stays at or above its safety stock.
2. The transfer arrives before the destination plant runs out.
3. The quantity does not exceed the shortage of the plan without order
   prioritization (no over-transfer).
4. Material and plants match the case.

Returns whether the STO is valid, the violations, the maximum feasible
quantity, and a validation_id.
"""
