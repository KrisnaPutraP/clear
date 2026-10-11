"""The agents' model on SAP AI Core (clear_agents.aicore): Strands' Bedrock model with its requests sent
to the AI Core deployment. Checked at the HTTP layer, without a network."""

import json

import pytest
from botocore.awsrequest import AWSResponse

from clear_agents import aicore, runner
from clear_tools import sap_rpt

SETTINGS = {
    "SAP_AICORE_AUTH_URL": "https://auth.example.test",
    "SAP_AICORE_CLIENT_ID": "client",
    "SAP_AICORE_CLIENT_SECRET": "secret",
    "SAP_AICORE_API_URL": "https://api.example.test/",
    "SAP_AICORE_RESOURCE_GROUP": "default",
    "SAP_LLM_DEPLOYMENT_ID": "d123",
}
ENDPOINT = "https://api.example.test/v2/inference/deployments/d123"


class _Body:  # A response body the way botocore reads it.
    def __init__(self, data: dict):
        self.data = json.dumps(data).encode()

    def stream(self, **kwargs):
        yield self.data


@pytest.fixture
def ai_core(monkeypatch):
    for name, value in SETTINGS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sap_rpt, "access_token", lambda config, timeout=10: "token-1")


def test_converse_goes_to_the_deployment_with_the_ai_core_token(ai_core):
    model = aicore.model("evidence")
    sent = []

    def answer(request, **kwargs):
        sent.append(request)
        return AWSResponse(request.url, 200, {"Content-Type": "application/json"}, _Body({
            "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 3, "outputTokens": 1, "totalTokens": 4},
            "metrics": {"latencyMs": 5},
        }))

    model.client.meta.events.register_last("before-send.bedrock-runtime.Converse", answer)
    response = model.client.converse(modelId=aicore.MODEL_NAME, messages=[{"role": "user", "content": [{"text": "hi"}]}])

    [request] = sent
    assert request.url == f"{ENDPOINT}/converse"
    assert request.headers["Authorization"] == "Bearer token-1"  # No AWS signature, no AWS credentials needed.
    assert request.headers["AI-Resource-Group"] == "default"
    assert response["output"]["message"]["content"] == [{"text": "ok"}]
    assert model.get_config()["streaming"] is False


def test_the_backend_setting_picks_the_model(ai_core, monkeypatch):
    monkeypatch.setenv("CLEAR_LLM_BACKEND", "aicore")
    assert runner.live_model("orchestrator").client.meta.endpoint_url == ENDPOINT
    assert runner.live_model_name() == f"SAP AI Core · {aicore.MODEL_NAME}"

    monkeypatch.setenv("CLEAR_LLM_BACKEND", "bedrock")
    monkeypatch.setenv("CLEAR_BEDROCK_MODEL_ID", "us.example.model-v1:0")
    assert runner.live_model("orchestrator").get_config()["model_id"] == "us.example.model-v1:0"

    monkeypatch.setenv("CLEAR_LLM_BACKEND", "elsewhere")
    with pytest.raises(LookupError, match="bedrock or aicore"):
        runner.live_model("orchestrator")


def test_a_missing_deployment_is_named(ai_core, monkeypatch):
    monkeypatch.delenv("SAP_LLM_DEPLOYMENT_ID")
    with pytest.raises(LookupError, match="SAP_LLM_DEPLOYMENT_ID"):
        aicore.model("evidence")
