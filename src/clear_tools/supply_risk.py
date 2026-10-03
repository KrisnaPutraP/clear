"""calculate_supply_risk (docs/PLAN.md §5c).

Deterministic. Scores a candidate plan given as IDs and decision variables
(priority level, transfer quantity, source plant). Stock and consumption are
read from the data store, and the predicted resolution time is looked up by
prediction_id.

- Required coverage = predicted resolution + port-to-plant transit.
- Coverage = (stock on hand + transfers arriving before stock runs out)
  / consumption of the orders served at the chosen priority level.
- Shortage = (required coverage - coverage) x consumption, if positive.
"""

from clear_tools import cases, planning, s4, sto
from clear_tools.store import JsonStore


def calculate_supply_risk(
    store: JsonStore,
    shipment_id: str,
    prediction_id: str,
    priority_level: str = "all",
    transfer_quantity: float = 0.0,
    source_plant: str | None = None,
) -> dict:
    """Coverage, shortage, deferred orders, and transfer cost of a candidate plan.

    priority_level is one of "all", "critical_high", or "critical".
    """
    case = cases.case(store, shipment_id)
    prediction = cases.prediction(store, prediction_id, shipment_id)
    transfer = _proposed_transfer(store, case, transfer_quantity, source_plant)
    return assess(store, case, prediction, priority_level, transfer)


def assess(
    store: JsonStore,
    case: cases.Case,
    prediction: dict,
    priority_level: str,
    transfer: dict | None = None,
) -> dict:
    """The calculation behind calculate_supply_risk, shared with validate_action."""
    served, deferred = planning.split_orders(store, case.material, case.plant, priority_level)
    consumption = round(sum(o["consumption_t_per_day"] for o in served), 3)
    if consumption <= 0:
        raise ValueError(f"No orders consume {case.material} at plant {case.plant} at level {priority_level!r}")

    on_hand = s4.stock(store, case.material, case.plant, s4.UNRESTRICTED)
    runout_days = on_hand / consumption
    inbound = sto.open_transfers(store, case.material, case.plant) + ([transfer] if transfer else [])
    arriving = [t for t in inbound if t["lead_time_days"] < runout_days]
    too_late = [t for t in inbound if t["lead_time_days"] >= runout_days]

    coverage = (on_hand + sum(t["quantity_t"] for t in arriving)) / consumption
    transit = planning.transit_days(store, case.port, case.plant)
    required = prediction["predicted_days"] + transit
    shortage = round(max(0.0, (required - coverage) * consumption), 1)

    return {
        "shipment_id": case.shipment["shipment_id"],
        "material": case.material,
        "plant": case.plant,
        "priority_level": priority_level,
        "required_coverage_days": round(required, 2),
        "coverage_days": round(coverage, 2),
        "covered": shortage == 0,
        "shortage_t": shortage,
        "consumption_t_per_day": consumption,
        "stock_on_hand_t": on_hand,
        "inbound_arriving": arriving,
        "inbound_too_late": too_late,
        "transfer": transfer,
        "deferred_orders": deferred,
        "prediction": {k: prediction[k] for k in ("prediction_id", "predicted_days", "source", "basis")},
        "port_to_plant_transit_days": transit,
        "sources": {
            "stock": f"S/4HANA (mock) {s4.STOCK.removeprefix('s4/')}",
            "consumption": f"{planning.ORDERS} (scenario data)",
            "prediction": prediction["source"],
            "transit_and_transfer": f"{planning.PARAMETERS} (scenario assumptions)",
        },
    }


def _proposed_transfer(
    store: JsonStore, case: cases.Case, quantity: float, source_plant: str | None
) -> dict | None:
    if not quantity:
        return None
    if quantity < 0:
        raise ValueError("transfer_quantity cannot be negative")
    if not source_plant:
        raise ValueError("source_plant is required when transfer_quantity is set")
    if source_plant == case.plant:
        raise ValueError(f"source_plant must differ from the receiving plant {case.plant}")
    cost_per_t = planning.transfer_cost_per_t(store, source_plant, case.plant)
    return {
        "status": "proposed",
        "quantity_t": float(quantity),
        "source_plant": source_plant,
        "lead_time_days": planning.sto_lead_time_days(store, source_plant, case.plant),
        "cost_usd": round(quantity * cost_per_t, 2),
    }
