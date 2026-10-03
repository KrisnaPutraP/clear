"""reconcile_documents trusts only extractions it can verify against the
document text (docs/PLAN.md §4b and the extraction risk in PLAN)."""

from clear_tools.read import get_documents
from clear_tools.reconcile import reconcile_documents

SHIPMENT = "SHP-1002"  # Documents agree, so any finding comes from the test.


def test_fabricated_quote_is_not_trusted(store, extract):
    extractions = extract(get_documents(store, SHIPMENT))
    extractions.append({"document_type": "packing_list", "field": "quantity", "value": 300.0,
                        "unit": "MT", "quote": "Quantity: 300 MT"})

    result = reconcile_documents(store, SHIPMENT, extractions)

    assert result["discrepancies"] == []
    assert [e["problem"] for e in result["unverified_extractions"]] == ["quote does not appear in the document"]


def test_value_must_appear_in_its_quote(store, extract):
    extractions = extract(get_documents(store, SHIPMENT))
    extractions.append({"document_type": "commercial_invoice", "field": "quantity", "value": 380.0,
                        "unit": "MT", "quote": "Quantity: 350 MT"})

    result = reconcile_documents(store, SHIPMENT, extractions)

    assert result["discrepancies"] == []
    assert [e["problem"] for e in result["unverified_extractions"]] == ["value does not appear in the quote"]


def test_kilograms_are_compared_in_tonnes(store, extract):
    extractions = [e for e in extract(get_documents(store, SHIPMENT))
                   if not (e["document_type"] == "packing_list" and e["field"] == "quantity")]
    extractions.append({"document_type": "packing_list", "field": "quantity", "value": 350000,
                        "unit": "KG", "quote": "Total Net Weight: 350,000 kg"})

    result = reconcile_documents(store, SHIPMENT, extractions)

    assert result["consistent"]


def test_missing_document_is_reported(store, extract):
    (store.root / "documents" / SHIPMENT / "certificate_of_analysis.txt").unlink()

    result = reconcile_documents(store, SHIPMENT, extract(get_documents(store, SHIPMENT)))

    assert result["missing_documents"] == ["certificate_of_analysis"]
    assert not result["consistent"]


def test_fields_left_unextracted_are_reported(store, extract):
    extractions = [e for e in extract(get_documents(store, SHIPMENT)) if e["field"] != "material"]

    result = reconcile_documents(store, SHIPMENT, extractions)

    assert not result["consistent"]
    assert {e["field"] for e in result["not_extracted"]} == {"material"}
