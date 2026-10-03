"""Logistics event feed, simulated (docs/PLAN.md §7a).

Not an agent tool. The demo's event feed records a prepared event here before
it starts the agent; in production the same payload would arrive from
EventBridge. Recording an event updates the shipment's status, ETA, and
exception, which is what the read and prediction tools see afterwards.
"""

from clear_tools import cases
from clear_tools.store import JsonStore

CATALOG = "logistics/event_catalog"


def prepared_event(store: JsonStore, event_id: str) -> dict:
    for event in store.read(CATALOG):
        if event["event_id"] == event_id:
            return event
    raise LookupError(f"Unknown event_id: {event_id}")


def record_event(store: JsonStore, event: dict) -> dict:
    """Apply a logistics event to its shipment and return the updated shipment."""
    shipments = store.read(cases.SHIPMENTS)
    shipment = next((s for s in shipments if s["shipment_id"] == event["shipment_id"]), None)
    if shipment is None:
        raise LookupError(f"Unknown shipment_id: {event['shipment_id']}")
    if any(e["event_id"] == event["event_id"] for e in shipment["events"]):
        return shipment  # Replaying an event changes nothing.

    details = event.get("details", {})
    if "exception_type" in details:
        shipment["status"] = "exception"
        shipment["exception"] = {
            "exception_type": details["exception_type"],
            "congestion_level": details["congestion_level"],
            "missing_documents": details.get("missing_documents", 0),
            "has_document_discrepancy": details.get("has_document_discrepancy", False),
            "raised_at": event["occurred_at"],
            "description": event["description"],
        }
    elif "congestion_level" in details and shipment["exception"]:
        shipment["exception"]["congestion_level"] = details["congestion_level"]
    if "new_eta" in details:
        shipment["eta"] = details["new_eta"]

    shipment["events"].append({
        "event_id": event["event_id"],
        "type": event["type"],
        "occurred_at": event["occurred_at"],
        "description": event["description"],
    })
    store.write(cases.SHIPMENTS, shipments)
    return shipment
