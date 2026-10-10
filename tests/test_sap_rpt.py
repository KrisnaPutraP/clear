"""The SAP-RPT-1.6 client builds the documented request and reads the
documented response (no network: the HTTP call is replaced)."""

import json

import pytest

from clear_tools import sap_rpt

CONFIG = sap_rpt.Config("https://auth.example", "client", "secret", "https://api.example", "default", "dep123")


def fake_post(response):
    calls = []

    def post(url, body, headers, timeout):
        calls.append({"url": url, "body": body, "headers": headers})
        return response

    return post, calls


def test_predict_sends_context_and_placeholder_rows(monkeypatch):
    response = {
        "status": {"code": 0, "message": "ok"},
        "predictions": [{"row_ref": "q0", "days": [{"prediction": 3.12, "confidence": None,
                                                    "confidence_interval": [2.5, 3.7]}]}],
        "explanations": {"top_column_scores": [{"port": 0.4}], "top_relevant_context_rows": [[1, 2]]},
    }
    post, calls = fake_post(response)
    monkeypatch.setattr(sap_rpt, "_post", post)

    [prediction] = sap_rpt.predict(
        CONFIG, [{"type": "a", "days": 1.0}, {"type": "b", "days": 2.0}], [{"type": "a"}], "days",
        token="t", explain_columns=1, explain_rows=2,
    )

    body = json.loads(calls[0]["body"])
    assert calls[0]["url"] == "https://api.example/v2/inference/deployments/dep123/predict"
    assert calls[0]["headers"]["AI-Resource-Group"] == "default"
    assert body["rows"][-1] == {"type": "a", "days": "[PREDICT]", "row_ref": "q0"}
    assert body["prediction_config"]["explanations"] == {"top_column_scores": 1, "top_relevant_context_rows": 2}
    assert prediction == sap_rpt.Prediction(3.12, (2.5, 3.7), {"port": 0.4}, [1])  # Row 2 is the query itself.


def test_error_status_is_raised(monkeypatch):
    post, _ = fake_post({"status": {"code": 3, "message": "bad request"}, "predictions": []})
    monkeypatch.setattr(sap_rpt, "_post", post)

    with pytest.raises(RuntimeError):
        sap_rpt.predict(CONFIG, [{"days": 1.0}], [{}], "days", token="t")


def test_config_reports_missing_settings_and_hides_the_secret(monkeypatch):
    for name in sap_rpt._SETTINGS.values():
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(LookupError):
        sap_rpt.Config.from_env()
    assert "secret" not in repr(CONFIG)
