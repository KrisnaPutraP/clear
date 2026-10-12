"""Names, tags, and settings of the deployment (docs/PLAN.md §8d).

Resources CLEAR creates itself use the team prefix cookusan-hackathon. The
AgentCore CLI allows only letters and digits in a project name and builds
the other names from it, so its resources start with cookusanhackathon.
Every resource carries the three required tags.
"""

import os

REGION = "us-west-2"
TAGS = {"Project": "ID-Hackathon-2026", "Team": "Cookusan", "DeleteAfter": "2026-10-31"}

# Created by scripts/aws_setup.py.
TABLE = "cookusan-hackathon-clear-data"
ACTION_ROLE = "cookusan-hackathon-action-agent"
# The Evidence and Impact agents sign their gateway calls with it when they run outside AgentCore Runtime.
AGENTS_ROLE = "cookusan-hackathon-agents"
SAP_PARAMETER = "/cookusan-hackathon/sap-aicore"

# Created by the AgentCore CLI from clear_aws.agentcore.
PROJECT = "cookusanhackathon"
RUNTIME = "clear"
GATEWAY = "tools"
TARGET = "clear-tools"
TOOL_SEPARATOR = "___"  # The gateway names a tool <target>___<tool>.
STACK_PREFIX = f"AgentCore-{PROJECT}-"  # CloudFormation stack per deployment target.

# Environment variables.
TABLE_SETTING = "CLEAR_DYNAMODB_TABLE"
ACTION_ROLE_SETTING = "CLEAR_ACTION_ROLE"
AGENTS_ROLE_SETTING = "CLEAR_AGENTS_ROLE"
RUNTIME_ARN_SETTING = "CLEAR_AGENT_RUNTIME_ARN"
GATEWAY_URL_SETTING = f"AGENTCORE_GATEWAY_{GATEWAY.upper()}_URL"  # Set on the runtime by the AgentCore CLI.
SAP_SETTINGS = ("SAP_AICORE_AUTH_URL", "SAP_AICORE_CLIENT_ID", "SAP_AICORE_CLIENT_SECRET", "SAP_AICORE_API_URL",
                "SAP_AICORE_RESOURCE_GROUP", "SAP_RPT_DEPLOYMENT_ID")


def region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or REGION


def table() -> str:
    return os.environ.get(TABLE_SETTING) or TABLE
