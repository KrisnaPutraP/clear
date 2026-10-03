"""Read tools (docs/PLAN.md §5a): get_shipment, get_purchase_order,
get_documents, get_inventory.

Purchase orders, stock, and safety stock come from the mock S/4HANA in
s4.py. Shipments and their events come from the simulated logistics event
feed, and documents are semi-structured text rendered from templates (§4b);
neither exists in the core S/4HANA APIs.
"""

from clear_tools import cases, planning, s4
from clear_tools.store import JsonStore


def get_shipment(store: JsonStore, shipment_id: str) -> dict:
    """Status, port, ETA, current exception, event history, and purchase order of a shipment."""
    return cases.shipment(store, shipment_id)


def get_purchase_order(store: JsonStore, purchase_order: str) -> dict:
    """Supplier, material, and quantity of a purchase order, as S/4HANA entities."""
    return s4.purchase_order(store, purchase_order)


def get_documents(store: JsonStore, shipment_id: str) -> dict:
    """Text of the shipment's documents plus the list of documents it should have."""
    required = cases.shipment(store, shipment_id)["required_documents"]
    documents = []
    for document_type in required:
        name = f"documents/{shipment_id}/{document_type}.txt"
        if store.exists(name):
            documents.append({"document_type": document_type, "text": store.read_text(name)})
    return {"shipment_id": shipment_id, "required_documents": required, "documents": documents}


def get_inventory(store: JsonStore, material: str) -> dict:
    """Stock and safety stock per plant, with daily consumption at each priority level."""
    plants = [
        {
            "plant": plant,
            "unrestricted_t": s4.stock(store, material, plant, s4.UNRESTRICTED),
            "in_transit_t": s4.stock(store, material, plant, s4.IN_TRANSIT),
            "safety_stock_t": s4.safety_stock(store, material, plant),
            "consumption_t_per_day": {
                level: planning.consumption_per_day(store, material, plant, level)
                for level in planning.PRIORITY_LEVELS
            },
            "orders": planning.orders(store, material, plant),
        }
        for plant in s4.plants_holding(store, material)
    ]
    if not plants:
        raise LookupError(f"No stock records for material {material}")
    return {
        "material": material,
        "plants": plants,
        "sources": {
            "stock": f"S/4HANA (mock) {s4.STOCK.removeprefix('s4/')}",
            "safety_stock": f"S/4HANA (mock) {s4.SUPPLY_PLANNING.removeprefix('s4/')}",
            "consumption": f"{planning.ORDERS} (scenario data)",
        },
    }
