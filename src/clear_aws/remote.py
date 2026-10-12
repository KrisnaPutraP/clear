"""Starting runs on AgentCore Runtime from the UI (docs/PLAN.md §7b).

Implements the Agents protocol of clear_app.contract. The UI records the
event or the decision in DynamoDB itself, asks the runtime to work the case
(clear_aws.runtime), and follows the case log as in a local run. One runtime
session per case and UI process keeps the runtime warm between a case's
runs.

GatewayAgents runs the same runtime code in this process instead, for an
account without AgentCore Runtime quota: the agents run here, their tools run
behind AgentCore Gateway, and the data stays in DynamoDB.
"""

import json
import os
import uuid
from collections.abc import Callable

import boto3
from botocore.config import Config

from clear_agents import caselog, runner
from clear_aws import runtime, settings
from clear_aws.gateway import Gateway

# A run takes minutes. Wait past the runtime's 15-minute request limit, and never retry:
# a retried invocation would start a second run of the same case.
CLIENT_CONFIG = Config(read_timeout=16 * 60, retries={"max_attempts": 1, "mode": "standard"})


class RuntimeAgents:
    def __init__(self, store, runtime_arn: str, client=None):
        self.store = store
        self.runtime_arn = runtime_arn
        self.client = client or boto3.client("bedrock-agentcore", region_name=settings.region(), config=CLIENT_CONFIG)
        self._session = uuid.uuid4().hex

    @classmethod
    def from_env(cls, store) -> "RuntimeAgents":
        arn = os.environ.get(settings.RUNTIME_ARN_SETTING)
        if not arn:
            raise LookupError(f"Set {settings.RUNTIME_ARN_SETTING} to the runtime ARN (docs/deployment.md)")
        return cls(store, arn)

    def work_event(self, case_id: str, event: dict) -> dict:
        return self._run(case_id, {"run": "event", "case_id": case_id, "event_id": event["event_id"]})

    def work_approval(self, case_id: str, approval: dict) -> dict:
        return self._run(case_id, {"run": "approval", "case_id": case_id, "approval_id": approval["approval_id"]})

    def _run(self, case_id: str, payload: dict) -> dict:
        try:
            response = self.client.invoke_agent_runtime(
                agentRuntimeArn=self.runtime_arn,
                runtimeSessionId=f"{self._session}-{case_id}",
                payload=json.dumps(payload).encode(),
                contentType="application/json",
                accept="application/json",
            )
            body = json.loads(response["response"].read() or b"{}")
            if response.get("statusCode", 200) >= 400 or "error" in body:
                raise RuntimeError(body.get("error") or f"HTTP {response.get('statusCode')}")
        except Exception as error:  # The case must not stay in "analyzing" when the runtime fails.
            return runner.fail(self.store, case_id, f"AgentCore Runtime: {type(error).__name__}: {error}")
        return caselog.get_case(self.store, case_id)


class GatewayAgents:
    """The runtime's work in this process: agents here, tools behind AgentCore Gateway (docs/deployment.md)."""

    def __init__(self, store, model_for: runner.ModelFactory = runner.live_model,
                 gateway: Callable[[], Gateway] | None = None):
        self.store, self.model_for, self.gateway = store, model_for, gateway

    def work_event(self, case_id: str, event: dict) -> dict:
        return self._run({"run": "event", "case_id": case_id, "event_id": event["event_id"]})

    def work_approval(self, case_id: str, approval: dict) -> dict:
        return self._run({"run": "approval", "case_id": case_id, "approval_id": approval["approval_id"]})

    def _run(self, payload: dict) -> dict:
        # Without a gateway factory, runtime.handle reads the gateway from the environment and, when it is
        # missing, fails the run readably.
        runtime.handle(payload, store=self.store, model_for=self.model_for,
                       gateway=self.gateway() if self.gateway else None)
        return caselog.get_case(self.store, payload["case_id"])
