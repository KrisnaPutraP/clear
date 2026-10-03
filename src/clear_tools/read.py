"""Read tools (docs/PLAN.md §5a): get_shipment, get_purchase_order,
get_documents, get_inventory.

Shipment, purchase order, and inventory records follow the structure of the
official S/4HANA APIs, limited to the fields the tools actually use (§4a).
Entity and field names are checked against the official SAP API documentation
at implementation time, never written from memory.

get_documents returns the document texts plus the list of documents the
shipment should have. Documents are semi-structured text rendered from
templates (§4b).
"""
