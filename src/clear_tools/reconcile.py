"""reconcile_documents (docs/PLAN.md §4b, §5a).

Deterministic. The LLM extracts fields from each shipping document and passes
them in with source quotes; this tool compares them in code, with each other
and with the purchase order, and returns the discrepancies and the missing
documents.

An extraction is trusted only if its quote appears in the document and its
value appears in the quote. Anything else is returned as unverified and left
out of the comparison, so a misread or invented value cannot create or hide
a discrepancy. Each result is stored with a reconciliation_id, together with
the verified quotes, so the UI can highlight the lines that disagree.
"""

import re

from clear_tools import cases, records, s4
from clear_tools.read import get_documents
from clear_tools.store import JsonStore

FIELDS = ("purchase_order", "material", "quantity")

# Fields each document type is expected to state.
EXPECTED_FIELDS = {
    "commercial_invoice": ("purchase_order", "material", "quantity"),
    "packing_list": ("purchase_order", "material", "quantity"),
    "bill_of_lading": ("purchase_order",),
    "certificate_of_analysis": ("material",),
}

TONNES_PER_UNIT = {"MT": 1.0, "T": 1.0, "TO": 1.0, "TNE": 1.0, "KG": 0.001}

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def reconcile_documents(store: JsonStore, shipment_id: str, extractions: list[dict]) -> dict:
    """Compare extracted document fields with each other and with the purchase order.

    Each extraction is {"document_type", "field", "value", "quote"}, plus
    "unit" for quantities. Fields: purchase_order, material, quantity.
    """
    case = cases.case(store, shipment_id)
    bundle = get_documents(store, shipment_id)
    texts = {doc["document_type"]: doc["text"] for doc in bundle["documents"]}
    item = s4.purchase_order(store, case.purchase_order)["A_PurchaseOrderItem"][0]
    reference = {
        "purchase_order": case.purchase_order,
        "material": case.material,
        "quantity": item["OrderQuantity"] * TONNES_PER_UNIT[item["PurchaseOrderQuantityUnit"]],
    }

    verified: dict[tuple[str, str], object] = {}
    quotes: dict[tuple[str, str], str] = {}
    unverified = []
    for extraction in extractions:
        problem = _problem(extraction, texts)
        if problem:
            unverified.append({**extraction, "problem": problem})
        else:
            key = (extraction["document_type"], extraction["field"])
            verified[key], quotes[key] = _normalized(extraction), str(extraction["quote"]).strip()

    discrepancies = []
    for field in FIELDS:
        values = {doc: value for (doc, f), value in verified.items() if f == field}
        mismatched = sorted(doc for doc, value in values.items() if not _same(value, reference[field]))
        if mismatched:
            discrepancies.append({
                "field": field,
                "purchase_order_value": reference[field],
                "document_values": values,
                "mismatched_documents": mismatched,
            })

    missing = [doc for doc in bundle["required_documents"] if doc not in texts]
    not_extracted = [
        {"document_type": doc, "field": field}
        for doc in texts
        for field in EXPECTED_FIELDS.get(doc, ())
        if (doc, field) not in verified
    ]
    return records.add(store, "reconciliation", {
        "shipment_id": shipment_id,
        "consistent": not (discrepancies or missing or not_extracted),
        "discrepancies": discrepancies,
        "missing_documents": missing,
        "unverified_extractions": unverified,
        "not_extracted": not_extracted,
        "verified_extractions": [
            {"document_type": doc, "field": field, "value": value, "quote": quotes[(doc, field)]}
            for (doc, field), value in verified.items()
        ],
        "purchase_order": {"source": f"S/4HANA (mock) {s4.PO_ITEMS.removeprefix('s4/')}", **reference},
    })


def _problem(extraction: dict, texts: dict[str, str]) -> str | None:
    """Why an extraction cannot be trusted, or None if it can."""
    field = extraction.get("field")
    if field not in FIELDS:
        return f"unknown field; expected one of {list(FIELDS)}"
    text = texts.get(extraction.get("document_type"))
    if text is None:
        return "no such document for this shipment"
    quote = str(extraction.get("quote") or "")
    if not quote.strip() or _squash(quote) not in _squash(text):
        return "quote does not appear in the document"
    value = extraction.get("value")
    if field == "quantity":
        if str(extraction.get("unit", "")).upper() not in TONNES_PER_UNIT:
            return f"unit must be one of {list(TONNES_PER_UNIT)}"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "quantity value must be a number"
        if not any(abs(n - number) < 1e-9 for n in _numbers(quote)):
            return "value does not appear in the quote"
    elif not str(value or "").strip() or str(value).strip().casefold() not in quote.casefold():
        return "value does not appear in the quote"
    return None


def _normalized(extraction: dict) -> object:
    if extraction["field"] == "quantity":
        return round(float(extraction["value"]) * TONNES_PER_UNIT[extraction["unit"].upper()], 3)
    return str(extraction["value"]).strip()


def _same(a: object, b: object) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) < 1e-6
    return str(a).casefold() == str(b).casefold()


def _squash(text: str) -> str:
    return " ".join(text.split()).casefold()


def _numbers(text: str) -> list[float]:
    return [float(match.replace(",", "")) for match in _NUMBER.findall(text)]
