"""Delete every AWS resource of the CLEAR deployment (docs/deployment.md, docs/PLAN.md §8d).

The AgentCore CLI's CloudFormation stack (runtime, gateway, Lambda function,
their roles), the DynamoDB table, the Action agent's IAM role, the SSM
parameter, and the log groups. With --include-bootstrap also the CDK
bootstrap stack with its S3 bucket and ECR repository; only for an account
that runs nothing else with CDK in us-west-2.

A dry run by default: it lists what it would delete, using read-only calls.
Nothing is deleted without --apply.

Usage:
    python scripts/aws_cleanup.py                       # dry run
    python scripts/aws_cleanup.py --apply
    python scripts/aws_cleanup.py --apply --include-bootstrap
"""

import argparse

import boto3

from clear_app import settings as app_settings
from clear_aws import provision, settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="delete")
    parser.add_argument("--include-bootstrap", action="store_true", help="also delete the CDK bootstrap stack")
    args = parser.parse_args()

    app_settings.load_env()
    session = boto3.Session(region_name=settings.REGION)
    identity = session.client("sts").get_caller_identity()
    print(f"Account {identity['Account']} as {identity['Arn']}, region {settings.REGION}")
    provision.run(provision.cleanup_steps(session.client, args.include_bootstrap), args.apply)


if __name__ == "__main__":
    main()
