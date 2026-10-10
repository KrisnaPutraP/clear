"""Display rules of the UI (clear_app.view), on a real scripted S1 case."""

import pytest

from clear_agents.testing import ScriptedDirector
from clear_app import view
from clear_app.contract import Clear


@pytest.fixture
def s1_case(store):
    clear = Clear(store, ScriptedDirector(store))
    return clear.get_case(clear.send_event("S1-DOC-HOLD", wait=True))


def test_option_rows_lead_with_the_current_plan_and_mark_the_recommendation(s1_case):
    rows = view.option_rows(s1_case["plan"])

    assert [r["option"] for r in rows][0] == "Current plan"
    assert [r["label"] for r in rows] == ["✕ short 160 t", "✕ short 60 t", "✓ covered"]
    assert [r["recommended"] for r in rows] == [False, False, True]
    assert rows[2]["orders_served"] == "Critical + high"


def test_document_lines_mark_the_disagreeing_quantity(s1_case):
    bundle = s1_case["documents"]
    documents = {d["document_type"]: d for d in
                 view.document_lines(bundle["documents"], bundle["required_documents"], s1_case["reconciliation"])}

    def marked(document_type):
        return [(line["text"].strip(), line["mark"]) for line in documents[document_type]["lines"] if line["mark"]]

    assert marked("packing_list") == [("Quantity: 560 MT", "mismatch")]
    assert marked("commercial_invoice") == [("Quantity: 600 MT", "reference")]
    assert marked("bill_of_lading") == []


def test_prediction_note_names_the_backend(s1_case):
    prediction = s1_case["plan"]["impact"]["prediction"]

    assert view.prediction_note(prediction).startswith("Baseline: median of")
    assert view.similar_cases(prediction) == []


def test_timeline_styles_validator_rejections_loudest(store):
    clear = Clear(store, ScriptedDirector(store))
    case_id = clear.send_event("S1-DOC-HOLD", wait=True)

    rows = view.timeline(clear.get_case_log(case_id))

    assert [(r["flag"], r["tone"]) for r in rows if r["flag"]] == [
        ("Document discrepancy", "warning"), ("Rejected by validator", "error"),
    ]
