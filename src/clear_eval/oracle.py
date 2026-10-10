"""The right decision for a variant, computed from the business rules (docs/PLAN.md §9c).

The oracle walks the same deterministic tools the agents use, on a scratch
copy of the store, so its own records never reach the run being scored:

1. Predict the resolution time and assess the current plan (all orders).
   Covered: keep the plan.
2. Otherwise validate a transfer of the whole shortage from the plant with
   the most stock above safety stock. Valid: transfer.
3. Otherwise, with a feasible partial quantity, serve fewer orders by
   priority until one level is covered: transfer and prioritize.
4. With no feasible transfer, serve fewer orders without one and escalate
   the deferred orders to a human (§6d); if even critical orders are not
   covered, escalate.

Evaluation runs use the baseline prediction, so ground truth is stable; the
SAP-RPT backend is evaluated separately (scripts/check_rpt_quality.py).
"""

import shutil
import tempfile
from pathlib import Path

from clear_tools import cases, s4
from clear_tools.events import prepared_event, record_event
from clear_tools.predict import predict_resolution_time
from clear_tools.store import JsonStore
from clear_tools.supply_risk import calculate_supply_risk
from clear_tools.validate import validate_action

LEVELS = ("all", "critical_high", "critical")


def expected(store: JsonStore, event_id: str) -> dict:
    """Decision class and its parameters for the event on this store."""
    with tempfile.TemporaryDirectory() as tmp:
        scratch = JsonStore(Path(tmp) / "scratch")
        shutil.copytree(store.root, scratch.root)
        return _expected(scratch, prepared_event(scratch, event_id))


def _expected(store: JsonStore, event: dict) -> dict:
    record_event(store, event)
    shipment_id = event["shipment_id"]
    case = cases.case(store, shipment_id)
    prediction_id = predict_resolution_time(store, shipment_id)["prediction_id"]
    current = calculate_supply_risk(store, shipment_id, prediction_id)
    result = {
        "shipment_id": shipment_id,
        "starts_with_documents": event["details"].get("exception_type") == "document_discrepancy",
        "shortage_before_t": current["shortage_t"],
        "decision": "keep_plan", "priority_level": "all", "source_plant": None, "quantity_t": 0.0,
    }
    if current["covered"]:
        return result

    sources = [plant for plant in s4.plants_holding(store, case.material) if plant != case.plant]
    checks = [(plant, validate_action(store, shipment_id, prediction_id, plant, current["shortage_t"]))
              for plant in sources]
    best = max(checks, key=lambda check: check[1]["max_feasible_quantity"], default=None)
    if best and best[1]["valid"]:
        return {**result, "decision": "transfer", "source_plant": best[0], "quantity_t": current["shortage_t"]}

    quantity = best[1]["max_feasible_quantity"] if best else 0.0
    source = best[0] if best and quantity > 0 else None
    for level in LEVELS[1:]:
        option = calculate_supply_risk(store, shipment_id, prediction_id, level, quantity, source)
        if option["covered"]:
            decision = "transfer_and_prioritize" if source else "prioritize_and_escalate"
            return {**result, "decision": decision, "priority_level": level, "source_plant": source,
                    "quantity_t": quantity}
    return {**result, "decision": "escalate", "priority_level": None, "source_plant": source, "quantity_t": quantity}
