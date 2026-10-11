"""Stand-ins for the AWS services CLEAR uses once deployed, for tests without an account.

Requests to DynamoDB and AgentCore Runtime are checked against the real API
models that botocore ships, so a misspelled parameter or a wrong attribute
shape fails a test as it would fail against AWS. FakeDeployment wires the UI,
the runtime, the gateway, and the Lambda function the way they are deployed,
with one store instance each over one table, as separate processes have.
"""

import copy
import functools
import io
import json
from pathlib import Path

import botocore.session
from botocore.exceptions import ClientError
from botocore.validate import validate_parameters

from clear_agents.testing import ScriptedDirector
from clear_app.contract import Clear
from clear_aws import gateway, lambda_tools, runtime, settings
from clear_aws.dynamo_store import DynamoStore, reset_table
from clear_aws.remote import RuntimeAgents

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"
RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/cookusanhackathon_clear-AbCdEf1234"


def check(service: str, operation: str, params: dict) -> None:
    validate_parameters(params, _input_shape(service, operation))


@functools.cache
def _input_shape(service: str, operation: str):
    return botocore.session.get_session().get_service_model(service).operation_model(operation).input_shape


class FakeDynamo:
    """In-memory DynamoDB table, for the requests DynamoStore makes. Scans return pages of page_size items."""

    def __init__(self, page_size: int = 10):
        self.items: dict[str, dict] = {}
        self.page_size = page_size
        self.calls: list[str] = []

    def get_item(self, **params) -> dict:
        self._check("GetItem", params)
        item = self.items.get(params["Key"]["name"]["S"])
        if item is None:
            return {}
        if "ProjectionExpression" in params:
            item = {"name": item["name"]}
        return {"Item": copy.deepcopy(item)}

    def update_item(self, **params) -> dict:
        self._check("UpdateItem", params)
        assert params["UpdateExpression"] == "SET #b = :b, #v = if_not_exists(#v, :zero) + :one"
        key, values = params["Key"]["name"]["S"], params["ExpressionAttributeValues"]
        current = self.items.get(key)
        if "ConditionExpression" in params:
            assert params["ConditionExpression"] == "#v = :seen"
            if current is None or current["version"]["N"] != values[":seen"]["N"]:
                raise ClientError({"Error": {"Code": "ConditionalCheckFailedException",
                                             "Message": "The conditional request failed"}}, "UpdateItem")
        version = {"N": str(int(current["version"]["N"]) + 1 if current else 1)}
        self.items[key] = {"name": {"S": key}, "body": values[":b"], "version": version}
        return {"Attributes": {"body": values[":b"], "version": version}}

    def delete_item(self, **params) -> dict:
        self._check("DeleteItem", params)
        self.items.pop(params["Key"]["name"]["S"], None)
        return {}

    def scan(self, **params) -> dict:
        self._check("Scan", params)
        assert params["ConsistentRead"] is True
        names = params["ExpressionAttributeNames"]
        attributes = [names[part.strip()] for part in params["ProjectionExpression"].split(",")]
        keys = sorted(self.items)
        start = keys.index(params["ExclusiveStartKey"]["name"]["S"]) + 1 if "ExclusiveStartKey" in params else 0
        page = keys[start:start + self.page_size]
        response = {"Items": [{a: copy.deepcopy(self.items[k][a]) for a in attributes} for k in page]}
        if start + self.page_size < len(keys):
            response["LastEvaluatedKey"] = {"name": {"S": page[-1]}}
        return response

    def _check(self, operation: str, params: dict) -> None:
        self.calls.append(operation)
        check("dynamodb", operation, params)


class FakeContext:
    """The Lambda context the gateway gives a tool call."""

    def __init__(self, tool_name: str):
        self.client_context = type("ClientContext", (), {"custom": {
            "bedrockAgentCoreToolName": tool_name, "bedrockAgentCoreGatewayId": "gw-1",
            "bedrockAgentCoreTargetId": "target-1", "bedrockAgentCoreMessageVersion": "1.0"}})()


class FakeGatewayClient:
    """An MCP session with the gateway, which runs each call in the tools' Lambda handler."""

    def __init__(self, credentials):
        self.credentials = credentials
        self.calls: list[str] = []
        self.started = self.stopped = False

    def start(self):
        self.started = True
        return self

    def stop(self, exc_type, exc_value, traceback) -> None:
        self.stopped = True

    def call_tool_sync(self, tool_use_id: str, name: str, arguments: dict, read_timeout_seconds=None) -> dict:
        target, _, tool = name.partition(settings.TOOL_SEPARATOR)
        assert target == settings.TARGET
        assert None not in arguments.values()  # A gateway schema cannot carry null.
        self.calls.append(tool)
        result = lambda_tools.lambda_handler(json.loads(json.dumps(arguments)), FakeContext(name))
        return {"status": "success", "toolUseId": tool_use_id, "content": [{"text": json.dumps(result)}]}


class FakeRuntimeClient:
    """The bedrock-agentcore client of the UI: each invocation runs the runtime's entrypoint logic."""

    def __init__(self, deployment: "FakeDeployment"):
        self.deployment = deployment
        self.invocations: list[dict] = []

    def invoke_agent_runtime(self, **params) -> dict:
        check("bedrock-agentcore", "InvokeAgentRuntime", params)
        self.invocations.append(params)
        store = self.deployment.runtime_store
        result = runtime.handle(json.loads(params["payload"]), store=store, model_for=ScriptedDirector(store),
                                gateway=self.deployment.gateway())
        return {"statusCode": 200, "contentType": "application/json", "runtimeSessionId": params["runtimeSessionId"],
                "response": io.BytesIO(json.dumps(result).encode())}


class FakeDeployment:
    """UI, runtime, gateway, and Lambda function over one table, each with its own store."""

    def __init__(self, monkeypatch):
        self.dynamo = FakeDynamo()
        self.ui_store, self.runtime_store, self.lambda_store = (DynamoStore(settings.TABLE, self.dynamo)
                                                                for _ in range(3))
        reset_table(SEED_DIR, self.ui_store)
        monkeypatch.setattr(lambda_tools, "_store", self.lambda_store)
        monkeypatch.setattr(gateway, "action_credentials", lambda role: f"credentials of {role}")
        self.gateway_clients: list[FakeGatewayClient] = []
        self.runtime_client = FakeRuntimeClient(self)

    def gateway(self) -> gateway.Gateway:
        return gateway.Gateway("https://gateway.example", settings.ACTION_ROLE, connect=self._connect)

    def clear(self) -> Clear:
        return Clear(self.ui_store, agents=RuntimeAgents(self.ui_store, RUNTIME_ARN, client=self.runtime_client))

    def _connect(self, credentials) -> FakeGatewayClient:
        client = FakeGatewayClient(credentials)
        self.gateway_clients.append(client)
        return client
