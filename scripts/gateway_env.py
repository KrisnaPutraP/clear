"""Print the .env lines that point the agents at the deployed gateway (docs/setup.md).

For a fresh clone, which has none of the AgentCore CLI's local state: the
gateway is looked up in AWS by its name. Needs only
bedrock-agentcore:ListGateways and bedrock-agentcore:GetGateway for the AWS
profile in .env, and changes nothing.

Usage:
    python scripts/gateway_env.py
"""

import sys

import boto3

from clear_app import settings as app_settings
from clear_aws import provision, settings


def main() -> None:
    app_settings.load_env()
    client = boto3.Session(region_name=settings.REGION).client("bedrock-agentcore-control")
    url = provision.gateway_url(client)
    if not url:
        sys.exit(f"No gateway named {settings.PROJECT}-{settings.GATEWAY} in {settings.REGION}; "
                 "it is not deployed (docs/deployment.md).")
    print("Add to .env:")
    print(f"{settings.GATEWAY_URL_SETTING}={url}")
    print(f"{settings.ACTION_ROLE_SETTING}={settings.ACTION_ROLE}")
    print(f"{settings.AGENTS_ROLE_SETTING}={settings.AGENTS_ROLE}")


if __name__ == "__main__":
    main()
