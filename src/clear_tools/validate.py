"""validate_action (docs/PLAN.md §5c).

Deterministic. Checks a proposed STO against the business rules:
1. Source plant stock after the transfer stays at or above its safety stock.
2. The transfer arrives before the receiving plant runs out.
3. The quantity does not exceed the shortage of the plan without order
   prioritization (no over-transfer).
4. Material and plants match the case.

Every validation is stored and returned with a validation_id, whether it
passes or not. Only a passing validation can be approved and turned into an
STO.
"""

from clear_tools import cases, planning, records, s4
from clear_tools.store import JsonStore
from clear_tools.supply_risk import assess


def validate_action(
    store: JsonStore, shipment_id: str, prediction_id: str, source_plant: str, quantity: float
) -> dict:
    """Validate an STO of `quantity` tonnes from `source_plant` to the case's plant."""
    case = cases.case(store, shipment_id)
    prediction = cases.prediction(store, prediction_id, shipment_id)
    violations: list[dict] = []
    checks: dict = {}
    max_feasible = 0.0

    if quantity <= 0:
        violations.append({"rule": "positive_quantity", "message": "Quantity must be greater than zero."})
    if source_plant == case.plant:
        violations.append({
            "rule": "plants_match_case",
            "message": f"Source plant must differ from the receiving plant {case.plant}.",
        })
    elif source_plant not in s4.plants_holding(store, case.material):
        violations.append({
            "rule": "plants_match_case",
            "message": f"Plant {source_plant} holds no {case.material}.",
        })
    else:
        source_stock = s4.stock(store, case.material, source_plant, s4.UNRESTRICTED)
        safety = s4.safety_stock(store, case.material, source_plant)
        lead_time = planning.sto_lead_time_days(store, source_plant, case.plant)
        unprioritized = assess(store, case, prediction, "all")
        runout = unprioritized["stock_on_hand_t"] / unprioritized["consumption_t_per_day"]
        shortage = unprioritized["shortage_t"]

        if source_stock - quantity < safety:
            violations.append({
                "rule": "source_safety_stock",
                "message": f"Plant {source_plant} would fall to {source_stock - quantity:g} t, "
                f"below its safety stock of {safety:g} t.",
            })
        if lead_time >= runout:
            violations.append({
                "rule": "arrives_before_stockout",
                "message": f"The transfer takes {lead_time:g} days, but plant {case.plant} "
                f"runs out in {runout:.2f} days.",
            })
        if quantity > shortage:
            violations.append({
                "rule": "no_over_transfer",
                "message": f"{quantity:g} t exceeds the {shortage:g} t shortage "
                "of the plan without order prioritization.",
            })
        max_feasible = round(max(0.0, min(source_stock - safety, shortage)), 1)
        checks = {
            "source_stock_t": source_stock,
            "source_safety_stock_t": safety,
            "lead_time_days": lead_time,
            "receiving_plant_runout_days": round(runout, 2),
            "shortage_without_prioritization_t": shortage,
        }

    return records.add(store, "validation", {
        "shipment_id": shipment_id,
        "prediction_id": prediction_id,
        "material": case.material,
        "material_text": case.material_text,
        "source_plant": source_plant,
        "destination_plant": case.plant,
        "quantity": float(quantity),
        "valid": not violations,
        "violations": violations,
        "max_feasible_quantity": max_feasible,
        "checks": checks,
    })
