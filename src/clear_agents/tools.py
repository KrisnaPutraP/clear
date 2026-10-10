"""Strands tools for the CLEAR agents (docs/PLAN.md §2a, §5a).

Each tool wraps a clear_tools function bound to one data store, so the LLM
passes only IDs and decision variables. Tools are grouped by agent, and only
the Action agent receives the write tool. Errors raised by clear_tools reach
the LLM as error results, so a governance refusal shows up in the trace.
"""

from typing import Literal

from pydantic import BaseModel, Field
from strands import tool

from clear_tools import predict, read, reconcile, sto, supply_risk, validate
from clear_tools.store import JsonStore


class Extraction(BaseModel):
    """One field read from one shipping document."""

    document_type: Literal["commercial_invoice", "packing_list", "bill_of_lading", "certificate_of_analysis"]
    field: Literal["purchase_order", "material", "quantity"]
    value: str | float = Field(description="The value as written in the document; a number for quantity.")
    unit: str | None = Field(default=None, description="Unit of a quantity as written, e.g. MT or kg.")
    quote: str = Field(description="The exact line of the document the value was read from.")


def _inline(schema: dict) -> dict:
    """Resolve $ref entries, so the schema needs no $defs."""
    definitions = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(definitions[node["$ref"].rsplit("/", 1)[-1]])
            return {key: resolve(value) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(value) for value in node]
        return node

    return resolve(schema)


RECONCILE_SCHEMA = {"json": {
    "type": "object",
    "properties": {
        "shipment_id": {"type": "string", "description": "Shipment ID, e.g. SHP-1001."},
        "extractions": {
            "type": "array",
            "description": "purchase_order, material, and quantity read from each document, with quotes.",
            "items": _inline(Extraction.model_json_schema()),
        },
    },
    "required": ["shipment_id", "extractions"],
}}


def evidence_tools(store: JsonStore) -> list:
    """Read tools plus document reconciliation (Evidence agent)."""

    @tool
    def get_shipment(shipment_id: str) -> dict:
        """Status, port of discharge, ETA, current exception, events, and purchase order of a shipment.

        Args:
            shipment_id: Shipment ID, e.g. SHP-1001.
        """
        return read.get_shipment(store, shipment_id)

    @tool
    def get_purchase_order(purchase_order: str) -> dict:
        """Supplier, material, plant, and quantity of a purchase order, as S/4HANA entities.

        Args:
            purchase_order: Purchase order number, e.g. 4500001021.
        """
        return read.get_purchase_order(store, purchase_order)

    @tool
    def get_documents(shipment_id: str) -> dict:
        """Text of the shipment's documents and the list of documents it should have.

        Args:
            shipment_id: Shipment ID.
        """
        return read.get_documents(store, shipment_id)

    @tool(inputSchema=RECONCILE_SCHEMA)
    def reconcile_documents(shipment_id: str, extractions: list[dict]) -> dict:
        """Compare fields you extracted from the documents with each other and with the purchase
        order. Returns discrepancies, missing documents, and any extraction whose quote or value
        could not be found in the document. Do not compare values yourself.
        """
        return reconcile.reconcile_documents(store, shipment_id, extractions)

    return [get_shipment, get_purchase_order, get_documents, _inventory_tool(store), reconcile_documents]


def impact_tools(store: JsonStore) -> list:
    """Prediction and supply-risk assessment (Impact & Options agent)."""

    @tool
    def predict_resolution_time(shipment_id: str) -> dict:
        """Predict how many days the shipment's current exception will take to resolve.
        Returns a prediction_id to cite, the predicted days, and the source of the number.

        Args:
            shipment_id: Shipment ID.
        """
        return predict.predict_resolution_time(store, shipment_id)

    @tool
    def calculate_supply_risk(
        shipment_id: str,
        prediction_id: str,
        priority_level: Literal["all", "critical_high", "critical"] = "all",
        transfer_quantity_t: float = 0.0,
        source_plant: str | None = None,
    ) -> dict:
        """Score one candidate plan: coverage, required coverage, shortage, deferred orders, and
        transfer cost. Returns an assessment_id to cite.

        Args:
            shipment_id: Shipment ID.
            prediction_id: ID returned by predict_resolution_time.
            priority_level: Orders served: all, critical_high (critical and high), or critical.
            transfer_quantity_t: Tonnes to transfer from another plant, 0 for none.
            source_plant: Plant the transfer comes from, required when transferring.
        """
        return supply_risk.calculate_supply_risk(
            store, shipment_id, prediction_id, priority_level, transfer_quantity_t, source_plant
        )

    return [predict_resolution_time, calculate_supply_risk]


def action_tools(store: JsonStore) -> list:
    """Validation, the STO write, and stock verification (Action agent)."""

    @tool
    def validate_action(shipment_id: str, prediction_id: str, source_plant: str, quantity_t: float) -> dict:
        """Check a proposed stock transport order against the business rules. Returns a
        validation_id, whether it is valid, any violations, and the maximum feasible quantity.

        Args:
            shipment_id: Shipment ID of the case.
            prediction_id: ID returned by predict_resolution_time.
            source_plant: Plant the stock would come from.
            quantity_t: Tonnes to transfer.
        """
        return validate.validate_action(store, shipment_id, prediction_id, source_plant, quantity_t)

    @tool
    def create_stock_transport_order(validation_id: str, approval_id: str) -> dict:
        """Create the stock transport order described by a passing validation that a human
        approved. Both IDs must come from the conversation; never invent an approval_id.

        Args:
            validation_id: ID returned by validate_action.
            approval_id: ID of the human approval for that validation.
        """
        return sto.create_stock_transport_order(store, validation_id, approval_id)

    return [validate_action, create_stock_transport_order, _inventory_tool(store)]


def _inventory_tool(store: JsonStore):
    @tool
    def get_inventory(material: str) -> dict:
        """Stock, stock in transit, and safety stock per plant, with daily consumption at each
        order priority level.

        Args:
            material: Material number, e.g. CHEM-BX40.
        """
        return read.get_inventory(store, material)

    return get_inventory
