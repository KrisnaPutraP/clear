"""The nine agent tools by name (docs/PLAN.md §5a, §5b).

One dispatch table for every place a tool runs: in-process during local
development, and in the Lambda function behind AgentCore Gateway once
deployed. Arguments use the parameter names the agents see, so a call means
the same thing wherever it runs.
"""

import inspect
from collections.abc import Callable

from clear_tools import predict, read, reconcile, sto, supply_risk, validate
from clear_tools.store import JsonStore


def _calculate_supply_risk(
    store: JsonStore,
    shipment_id: str,
    prediction_id: str,
    priority_level: str = "all",
    transfer_quantity_t: float = 0.0,
    source_plant: str | None = None,
) -> dict:
    return supply_risk.calculate_supply_risk(
        store, shipment_id, prediction_id, priority_level, transfer_quantity_t, source_plant
    )


def _validate_action(store: JsonStore, shipment_id: str, prediction_id: str, source_plant: str,
                     quantity_t: float) -> dict:
    return validate.validate_action(store, shipment_id, prediction_id, source_plant, quantity_t)


TOOLS: dict[str, Callable[..., dict]] = {
    "get_shipment": read.get_shipment,
    "get_purchase_order": read.get_purchase_order,
    "get_documents": read.get_documents,
    "get_inventory": read.get_inventory,
    "reconcile_documents": reconcile.reconcile_documents,
    "predict_resolution_time": predict.predict_resolution_time,
    "calculate_supply_risk": _calculate_supply_risk,
    "validate_action": _validate_action,
    "create_stock_transport_order": sto.create_stock_transport_order,
}


def call(store: JsonStore, name: str, arguments: dict) -> dict:
    """Run one tool. Raises LookupError for an unknown tool and ValueError for bad arguments."""
    tool = TOOLS.get(name)
    if tool is None:
        raise LookupError(f"Unknown tool: {name}")
    try:
        inspect.signature(tool).bind(store, **arguments)
    except TypeError as error:
        raise ValueError(f"Invalid arguments for {name}: {error}") from None
    return tool(store, **arguments)
