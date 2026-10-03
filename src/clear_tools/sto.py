"""create_stock_transport_order (docs/PLAN.md §1c, §5a, §6).

The only write tool. Creates an STO from a validation_id and an approval_id,
so the quantity written is exactly the quantity that was validated and
approved by a human. The posting moves the quantity out of the source
plant's unrestricted stock into stock in transit at the receiving plant;
the Action agent then verifies positions with get_inventory.
"""

from clear_tools import planning, records, s4
from clear_tools.store import JsonStore

EXECUTED = "records/stock_transport_orders"


def create_stock_transport_order(store: JsonStore, validation_id: str, approval_id: str) -> dict:
    """Create the STO that a passing validation describes and a human approved."""
    validation = records.get(store, "validation", validation_id)
    approval = records.get(store, "approval", approval_id)
    if approval["validation_id"] != validation_id:
        raise PermissionError(f"{approval_id} approves {approval['validation_id']}, not {validation_id}.")
    if approval["decision"] != "approved":
        raise PermissionError(f"{approval_id} rejected {validation_id}.")
    if not validation["valid"]:
        raise PermissionError(f"{validation_id} failed validation.")
    executed = store.read(EXECUTED)
    if any(record["validation_id"] == validation_id for record in executed):
        raise PermissionError(f"{validation_id} has already been executed.")

    material = validation["material"]
    source, destination = validation["source_plant"], validation["destination_plant"]
    quantity = validation["quantity"]
    # Stock may have moved since validation, e.g. through another STO.
    if s4.stock(store, material, source, s4.UNRESTRICTED) - quantity < s4.safety_stock(store, material, source):
        raise PermissionError(f"Stock at plant {source} changed since {validation_id}; validate again.")

    number = s4.insert_stock_transport_order(
        store, source, destination, material, quantity, validation["material_text"]
    )
    s4.post_stock_change(store, material, source, s4.UNRESTRICTED, -quantity)
    s4.post_stock_change(store, material, destination, s4.IN_TRANSIT, quantity)

    result = {
        "purchase_order": number,
        "purchase_order_type": s4.STO,
        "material": material,
        "quantity_t": quantity,
        "source_plant": source,
        "destination_plant": destination,
        "lead_time_days": planning.sto_lead_time_days(store, source, destination),
        "validation_id": validation_id,
        "approval_id": approval_id,
    }
    executed.append({**result, "created_at": records.now()})
    store.write(EXECUTED, executed)
    return result


def open_transfers(store: JsonStore, material: str, plant: str) -> list[dict]:
    """STOs on their way to the plant; goods receipt is not simulated."""
    return [
        {
            "status": "in_transit",
            "purchase_order": record["purchase_order"],
            "quantity_t": record["quantity_t"],
            "source_plant": record["source_plant"],
            "lead_time_days": record["lead_time_days"],
        }
        for record in store.read(EXECUTED)
        if record["material"] == material and record["destination_plant"] == plant
    ]
