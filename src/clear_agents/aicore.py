"""Claude on SAP AI Core as the agents' model (docs/PLAN.md §8b).

SAP AI Core serves Anthropic models with the Bedrock Converse API; SAP's own
samples call them through a Bedrock client. So the agents keep Strands'
Bedrock model and only its client changes: each request goes to the team's
AI Core deployment, unsigned, with the AI Core access token in place of an
AWS signature. Streaming is off, so the deployment's converse path is the
only one used.

Credentials are the team's AI Core service key, the same as for SAP-RPT-1.6
(clear_tools.sap_rpt). SAP_LLM_DEPLOYMENT_ID names the chat model's
deployment.
"""

import functools

import boto3
from botocore import UNSIGNED
from botocore.config import Config as BotocoreConfig
from strands.models import BedrockModel

from clear_tools import sap_rpt

DEPLOYMENT_SETTING = "SAP_LLM_DEPLOYMENT_ID"
MODEL_NAME = "anthropic--claude-4.6-sonnet"  # The deployment decides the model; this only names it.


def model(role: str) -> BedrockModel:
    config = sap_rpt.Config.from_env(DEPLOYMENT_SETTING)
    endpoint = f"{config.api_url.rstrip('/')}/v2/inference/deployments/{config.deployment_id}"
    session = boto3.Session(region_name="us-west-2")  # botocore needs a region; AI Core ignores it.
    session.events.register("before-send.bedrock-runtime.Converse", functools.partial(_to_ai_core, config, endpoint))
    return BedrockModel(
        model_id=MODEL_NAME,
        boto_session=session,
        boto_client_config=BotocoreConfig(signature_version=UNSIGNED, read_timeout=120,
                                          retries={"mode": "standard", "max_attempts": 4}),
        endpoint_url=endpoint,
        streaming=False,
        include_tool_result_status=True,  # As Strands does for Claude on Bedrock.
    )


def _to_ai_core(config: sap_rpt.Config, endpoint: str, request, **kwargs) -> None:
    """Send a Converse request to the deployment, authorized with the AI Core token."""
    request.url = f"{endpoint}/converse"
    request.headers["Authorization"] = f"Bearer {sap_rpt.access_token(config)}"
    request.headers["AI-Resource-Group"] = config.resource_group
