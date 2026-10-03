"""predict_resolution_time, Level 2 baseline (docs/PLAN.md §3c)."""

import pytest

from clear_tools import planning
from clear_tools.events import prepared_event, record_event
from clear_tools.predict import predict_resolution_time

SHIPMENT = "SHP-1001"


def test_prediction_needs_an_active_exception(store):
    with pytest.raises(ValueError):
        predict_resolution_time(store, SHIPMENT)


def test_prediction_states_its_source_and_basis(store):
    record_event(store, prepared_event(store, "S1-DOC-HOLD"))

    prediction = predict_resolution_time(store, SHIPMENT)

    assert prediction["prediction_id"] == "PRED-0001"
    assert prediction["source"] == "baseline-median"
    assert prediction["basis"]["grouped_by"] == {
        "exception_type": "document_discrepancy", "port": "Tanjung Priok", "congestion_level": "normal"
    }
    assert prediction["basis"]["cases"] >= planning.baseline_min_group_size(store)


def test_small_groups_fall_back_to_type_and_port(store):
    parameters = store.read(planning.PARAMETERS)
    parameters["baseline_min_group_size"] = 50  # Above the S1 high-congestion group.
    store.write(planning.PARAMETERS, parameters)
    record_event(store, prepared_event(store, "S1-DOC-HOLD"))
    record_event(store, prepared_event(store, "S1-ETA-SLIP"))

    prediction = predict_resolution_time(store, SHIPMENT)

    assert prediction["basis"]["grouped_by"] == {"exception_type": "document_discrepancy", "port": "Tanjung Priok"}


def test_replaying_an_event_changes_nothing(store):
    event = prepared_event(store, "S1-DOC-HOLD")
    first = record_event(store, event)

    assert record_event(store, event) == first
