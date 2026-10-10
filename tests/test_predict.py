"""predict_resolution_time: Level 2 baseline and the SAP-RPT fallback chain (docs/PLAN.md §3c)."""

import pytest

from clear_tools import planning, sap_rpt
from clear_tools.events import prepared_event, record_event
from clear_tools.predict import predict_resolution_time

SHIPMENT = "SHP-1001"


@pytest.fixture
def rpt(monkeypatch):
    """SAP-RPT switched on, with the AI Core call replaced; set rpt.answer to a Prediction or an exception."""

    class Fake:
        answer: object = sap_rpt.Prediction(3.14, (2.62, 3.71), None, [0, 1])
        calls = 0

        def predict(self, config, context, queries, target, **kwargs):
            self.calls += 1
            if isinstance(self.answer, Exception):
                raise self.answer
            return [self.answer]

    fake = Fake()
    monkeypatch.setenv("CLEAR_PREDICTION_BACKEND", "auto")
    monkeypatch.setattr(sap_rpt.Config, "from_env", classmethod(lambda cls: "config"))
    monkeypatch.setattr(sap_rpt, "access_token", lambda config, timeout: "token")
    monkeypatch.setattr(sap_rpt, "predict", fake.predict)
    return fake


def test_rpt_prediction_carries_its_interval_and_similar_cases(store, rpt):
    record_event(store, prepared_event(store, "S1-DOC-HOLD"))

    prediction = predict_resolution_time(store, SHIPMENT)

    assert prediction["source"] == "sap-rpt-1.6"
    assert prediction["predicted_days"] == 3.1
    assert prediction["basis"]["interval_days"] == [2.6, 3.7]
    assert len(prediction["basis"]["similar_cases"]) == 2


def test_rpt_failure_falls_back_to_the_baseline_with_the_reason(store, rpt):
    rpt.answer = TimeoutError("timed out")
    record_event(store, prepared_event(store, "S1-DOC-HOLD"))

    prediction = predict_resolution_time(store, SHIPMENT)

    assert prediction["source"] == "baseline-median"
    assert prediction["basis"]["fallback_reason"] == "TimeoutError: timed out"


def test_baseline_is_the_default_and_never_calls_rpt(store, rpt, monkeypatch):
    monkeypatch.delenv("CLEAR_PREDICTION_BACKEND")
    record_event(store, prepared_event(store, "S1-DOC-HOLD"))

    assert predict_resolution_time(store, SHIPMENT)["source"] == "baseline-median"
    assert rpt.calls == 0


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
