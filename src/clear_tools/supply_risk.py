"""calculate_supply_risk (docs/PLAN.md §5c).

Deterministic. Scores a candidate plan given as IDs and decision variables
(transfer quantity, order priority level). Stock and consumption are read from
the data store, and the predicted resolution time is looked up by
prediction_id. Returns required coverage, coverage, shortage, deferred orders,
and transfer cost.
"""
