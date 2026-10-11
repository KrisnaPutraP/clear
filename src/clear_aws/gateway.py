"""The agents' tools through AgentCore Gateway (docs/PLAN.md §2a, §5b, §6a).

Deployed agents keep the Strands tools of local development, with the same
names, descriptions, and input schemas (clear_agents.tools); only the call
travels, to the Lambda function behind the gateway (clear_aws.lambda_tools),
over MCP signed with SigV4. A tool's error comes back as the exception the
tool raised, so the agents and the case log read the same text as in a
local run.

The Action agent, the only one with the write tool, signs its calls with its
own IAM role, so the gateway's Cedar policy can tell its calls apart from
the other agents' (docs/PLAN.md §6a).
"""

import builtins
import json
import os
import uuid
from collections.abc import Callable
from datetime import timedelta

import boto3
from botocore.credentials import Credentials

from clear_agents.tools import Invoke
from clear_aws import settings

TIMEOUT = timedelta(seconds=90)  # A prediction may wait 15 s for SAP-RPT-1.6, plus a Lambda cold start.


class GatewayError(RuntimeError):
    """The gateway itself refused or failed a call, for example on a policy decision."""


class Gateway:
    """MCP sessions with the gateway: one signed with the runtime's role, one with the Action agent's.

    Used as a context manager around one run; it gives role -> Invoke, as clear_agents.runner expects.
    """

    def __init__(self, url: str, action_role: str | None = None, connect: Callable | None = None):
        self.url = url
        self.action_role = action_role
        self._connect = connect or self._mcp_client  # Credentials, None for the runtime's own -> MCP client.
        self._clients: dict[str, object] = {}

    @classmethod
    def from_env(cls) -> "Gateway":
        url = os.environ.get(settings.GATEWAY_URL_SETTING)
        if not url:
            raise LookupError(f"{settings.GATEWAY_URL_SETTING} is not set; the AgentCore CLI sets it on the runtime")
        return cls(url, os.environ.get(settings.ACTION_ROLE_SETTING) or None)

    def __enter__(self) -> Callable[[str], Invoke]:
        try:
            self._clients["agents"] = self._start(None)
            self._clients["action"] = (self._start(action_credentials(self.action_role))
                                       if self.action_role else self._clients["agents"])
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return lambda role: _invoke(self._clients["action" if role == "action" else "agents"])

    def __exit__(self, *exc_info) -> None:
        for client in {id(client): client for client in self._clients.values()}.values():
            client.stop(None, None, None)
        self._clients = {}

    def _start(self, credentials: Credentials | None):
        client = self._connect(credentials)
        client.start()
        return client

    def _mcp_client(self, credentials: Credentials | None):
        # Imported here: both packages are in the runtime bundle, not in the local development setup.
        from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
        from strands.tools.mcp import MCPClient

        return MCPClient(lambda: aws_iam_streamablehttp_client(
            self.url, aws_service="bedrock-agentcore", aws_region=settings.region(), credentials=credentials,
            timeout=TIMEOUT))


def action_credentials(role: str) -> Credentials:
    """Temporary credentials of the Action agent's IAM role, given its name or ARN."""
    sts = boto3.client("sts", region_name=settings.region())
    arn = role if role.startswith("arn:") else f"arn:aws:iam::{sts.get_caller_identity()['Account']}:role/{role}"
    issued = sts.assume_role(RoleArn=arn, RoleSessionName="clear-action-agent")["Credentials"]
    return Credentials(issued["AccessKeyId"], issued["SecretAccessKey"], issued["SessionToken"])


def _invoke(client) -> Invoke:
    def invoke(name: str, arguments: dict) -> dict:
        # The gateway's schemas cannot express null: an argument left out takes the tool's default.
        sent = {key: value for key, value in arguments.items() if value is not None}
        result = client.call_tool_sync(f"clear-{uuid.uuid4().hex}", f"{settings.TARGET}{settings.TOOL_SEPARATOR}{name}",
                                       sent, read_timeout_seconds=TIMEOUT)
        text = "".join(block.get("text", "") for block in result.get("content", []))
        if result.get("status") == "error":
            raise GatewayError(text or f"The gateway failed {name}")
        return unpack(name, text)

    return invoke


def unpack(name: str, text: str) -> dict:
    """The tool's result from the text the gateway returned, or the tool's exception raised again."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        raise GatewayError(f"Unexpected response from the gateway for {name}: {text[:200]}")
    if set(payload) == {"error"}:
        error = payload["error"]
        raise _exception(error if isinstance(error, dict) else {"message": error})
    return payload


def _exception(error: dict) -> Exception:
    """An exception of the type the tool raised, so Strands words the error as in a local run."""
    name = str(error.get("type", ""))
    kind = getattr(builtins, name, None)
    if not (isinstance(kind, type) and issubclass(kind, Exception)):
        kind = type(name if name.isidentifier() else "ToolError", (RuntimeError,), {})
    return kind(str(error.get("message", "")))
