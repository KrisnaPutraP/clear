"""The tools' Lambda function behind AgentCore Gateway (docs/PLAN.md §5b).

A thin wrapper around clear_tools.catalog. The gateway passes the tool's
arguments as the event and its name, prefixed with the target name, in the
client context. A failure comes back as an error object, not a raised
exception: the gateway replaces exception details with a generic message,
and the agents must be able to read why a step was refused.

Lambda functions made by the AgentCore CLI get no environment variables, so
the table name comes from clear_aws.settings and the SAP AI Core service key
from an SSM SecureString parameter, read once per container. Without the
key, predictions fall back to the baseline and say so (docs/PLAN.md §3c).
Only the standard library, boto3, and clear_tools are imported, all of which
the Lambda Python runtime provides or the bundle carries.
"""

import json
import logging
import os

import boto3

from clear_aws import settings
from clear_aws.dynamo_store import DynamoStore
from clear_tools import catalog, predict

logger = logging.getLogger(__name__)
_store: DynamoStore | None = None


def lambda_handler(event: dict, context) -> dict:
    name = _tool_name(context)
    try:
        return catalog.call(_prepared_store(), name, event)
    except Exception as error:  # Every failure reaches the agent as a readable result.
        logger.warning("%s failed: %s: %s", name, type(error).__name__, error)
        return {"error": {"type": type(error).__name__, "message": str(error)}}


def _tool_name(context) -> str:
    custom = getattr(getattr(context, "client_context", None), "custom", None) or {}
    return str(custom.get("bedrockAgentCoreToolName", "")).split(settings.TOOL_SEPARATOR, 1)[-1]


def _prepared_store() -> DynamoStore:
    global _store
    if _store is None:
        _load_sap_settings()
        os.environ.setdefault(predict.BACKEND_SETTING, "auto")
        _store = DynamoStore.from_env()
    return _store


def _load_sap_settings() -> None:
    """Put the SAP AI Core service key from SSM into the environment, where clear_tools.sap_rpt reads it."""
    try:
        parameter = boto3.client("ssm", region_name=settings.region()).get_parameter(
            Name=settings.SAP_PARAMETER, WithDecryption=True)
        values = json.loads(parameter["Parameter"]["Value"])
    except Exception as error:  # Predictions still work, from the baseline.
        logger.warning("SAP AI Core key unavailable (%s); predictions use the baseline", type(error).__name__)
        return
    for name in settings.SAP_SETTINGS:
        if values.get(name):
            os.environ.setdefault(name, str(values[name]))
