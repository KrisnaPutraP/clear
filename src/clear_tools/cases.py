"""Case context (docs/PLAN.md §5a).

A case is one shipment exception. Deterministic tools take a shipment_id and
derive the material, receiving plant, and port from the shipment and its
purchase order, so the LLM never passes those values itself. Shipments are
expected to carry single-item purchase orders.
"""

from dataclasses import dataclass

from clear_tools import records, s4
from clear_tools.store import JsonStore

SHIPMENTS = "logistics/shipments"


@dataclass(frozen=True)
class Case:
    shipment: dict
    purchase_order: str
    material: str
    material_text: str
    plant: str
    port: str


def shipment(store: JsonStore, shipment_id: str) -> dict:
    for record in store.read(SHIPMENTS):
        if record["shipment_id"] == shipment_id:
            return record
    raise LookupError(f"Unknown shipment_id: {shipment_id}")


def case(store: JsonStore, shipment_id: str) -> Case:
    record = shipment(store, shipment_id)
    item = s4.purchase_order(store, record["purchase_order"])["A_PurchaseOrderItem"][0]
    return Case(
        shipment=record,
        purchase_order=record["purchase_order"],
        material=item["Material"],
        material_text=item["PurchaseOrderItemText"],
        plant=item["Plant"],
        port=record["port_of_discharge"],
    )


def prediction(store: JsonStore, prediction_id: str, shipment_id: str) -> dict:
    """The prediction record, checked to belong to this shipment."""
    record = records.get(store, "prediction", prediction_id)
    if record["shipment_id"] != shipment_id:
        raise ValueError(f"{prediction_id} was made for {record['shipment_id']}, not {shipment_id}")
    return record
