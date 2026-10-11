"""Create what the AgentCore CLI does not, then load the seed data (docs/deployment.md).

The DynamoDB table, the Action agent's IAM role, and the SSM SecureString
parameter holding the SAP AI Core key from .env, all tagged Project, Team,
and DeleteAfter in us-west-2. Then the table is reset to data/seed/.

A dry run by default: it shows what exists and what it would change, using
read-only calls. Nothing changes without --apply.

Usage:
    python scripts/aws_setup.py            # dry run
    python scripts/aws_setup.py --apply
"""

import argparse
import os

import boto3

from clear_app import settings as app_settings
from clear_aws import provision, settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="make the changes")
    args = parser.parse_args()

    app_settings.load_env()
    session = boto3.Session(region_name=settings.REGION)
    identity = session.client("sts").get_caller_identity()
    print(f"Account {identity['Account']} as {identity['Arn']}, region {settings.REGION}")
    sap_key = {name: os.environ.get(name, "") for name in settings.SAP_SETTINGS}
    steps = provision.setup_steps(session.client, identity["Account"], sap_key, app_settings.SEED_DIR)
    provision.run(steps, args.apply)

    arn = provision.deployed(app_settings.REPO_ROOT / "deploy" / settings.PROJECT).get("runtime_arn")
    if arn:
        print(f"\nFor the UI, add to .env:\n{settings.RUNTIME_ARN_SETTING}={arn}")


if __name__ == "__main__":
    main()
