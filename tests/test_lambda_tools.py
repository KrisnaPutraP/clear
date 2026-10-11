"""The tools' Lambda function behind AgentCore Gateway (docs/PLAN.md §5b): a thin wrapper that
runs the tool the gateway names and returns failures as readable results."""

import json
import logging

import pytest
from botocore.exceptions import ClientError

from aws_fakes import SEED_DIR, FakeContext, FakeDynamo
from clear_aws import lambda_tools, settings
from clear_aws.dynamo_store import DynamoStore, reset_table
from clear_tools import catalog


@pytest.fixture
def lambda_store(monkeypatch):
    store = DynamoStore(settings.TABLE, FakeDynamo())
    reset_table(SEED_DIR, store)
    monkeypatch.setattr(lambda_tools, "_store", store)
    return store


def call(tool: str, event: dict) -> dict:
    return lambda_tools.lambda_handler(event, FakeContext(f"{settings.TARGET}___{tool}"))


def test_runs_the_tool_the_gateway_names(lambda_store, store):
    assert call("get_shipment", {"shipment_id": "SHP-1001"}) == catalog.call(store, "get_shipment",
                                                                            {"shipment_id": "SHP-1001"})


def test_failures_come_back_as_error_results(lambda_store):
    refused = call("create_stock_transport_order", {"validation_id": "VAL-0001", "approval_id": "APR-0001"})
    assert refused == {"error": {"type": "LookupError", "message": "Unknown validation_id: VAL-0001"}}

    assert call("drop_tables", {})["error"]["message"] == "Unknown tool: drop_tables"
    assert call("get_shipment", {})["error"]["type"] == "ValueError"
    assert lambda_tools.lambda_handler({}, object())["error"]["type"] == "LookupError"  # No tool name at all.


class FakeSsm:
    def __init__(self, value: dict | None):
        self.value = value

    def get_parameter(self, Name, WithDecryption):
        assert (Name, WithDecryption) == (settings.SAP_PARAMETER, True)
        if self.value is None:
            raise ClientError({"Error": {"Code": "ParameterNotFound", "Message": "missing"}}, "GetParameter")
        return {"Parameter": {"Value": json.dumps(self.value)}}


@pytest.fixture
def clean_environment(monkeypatch):
    for name in (*settings.SAP_SETTINGS, "CLEAR_PREDICTION_BACKEND"):
        monkeypatch.setenv(name, "")  # Records the original state, so what the handler sets is undone.
        monkeypatch.delenv(name)
    monkeypatch.setattr(lambda_tools, "_store", None)
    monkeypatch.setattr(lambda_tools.DynamoStore, "from_env", classmethod(lambda cls: "store"))


def test_first_call_loads_the_sap_key_from_ssm(monkeypatch, clean_environment):
    key = {name: f"value of {name}" for name in settings.SAP_SETTINGS}
    monkeypatch.setattr(lambda_tools.boto3, "client", lambda service, region_name: FakeSsm(key))

    assert lambda_tools._prepared_store() == "store"

    assert all(lambda_tools.os.environ[name] == value for name, value in key.items())
    assert lambda_tools.os.environ["CLEAR_PREDICTION_BACKEND"] == "auto"


def test_without_the_sap_key_predictions_use_the_baseline(monkeypatch, clean_environment, caplog):
    monkeypatch.setattr(lambda_tools.boto3, "client", lambda service, region_name: FakeSsm(None))

    with caplog.at_level(logging.WARNING):
        lambda_tools._prepared_store()

    assert not any(name in lambda_tools.os.environ for name in settings.SAP_SETTINGS)
    assert "predictions use the baseline" in caplog.text
