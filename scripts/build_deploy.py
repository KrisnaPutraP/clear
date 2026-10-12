"""Assemble the AgentCore CLI project for deployment (docs/deployment.md).

Writes agentcore.json, the runtime's code location (agents), and the Lambda
function's code location (tools) into deploy/cookusanhackathon/, the project
directory that `agentcore create` made, and fills the CLI's empty deployment
target with your account (read with STS) and us-west-2. Nothing is created
in AWS until you run `agentcore deploy` in that directory.

With --policy, agentcore.json also attaches the Cedar policies to the gateway
(docs/PLAN.md §6a). They name the deployed gateway and the role the agents
sign with (the runtime's, or with --no-runtime the agents role), so deploy
once without --policy first.

Usage:
    python scripts/build_deploy.py
    python scripts/build_deploy.py --policy log-only    # decisions logged, not applied
    python scripts/build_deploy.py --policy enforce
    python scripts/build_deploy.py --no-runtime --policy log-only   # agents outside the runtime
"""

import argparse
import json
import os
import sys

import boto3

from clear_app import settings as app_settings
from clear_aws import agentcore, provision, settings
from clear_aws.policy import account

PROJECT_DIR = app_settings.REPO_ROOT / "deploy" / settings.PROJECT
MODES = {"log-only": "LOG_ONLY", "enforce": "ENFORCE"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", choices=sorted(MODES), help="attach the Cedar policies to the gateway")
    parser.add_argument("--no-runtime", action="store_true",
                        help="gateway and Lambda only; the agents run where the UI runs (no Runtime quota)")
    args = parser.parse_args()

    app_settings.load_env()
    model_id = os.environ.get("CLEAR_BEDROCK_MODEL_ID")
    if not model_id:
        sys.exit("Set CLEAR_BEDROCK_MODEL_ID in .env first: the runtime's agents need it.")
    if not (PROJECT_DIR / "agentcore" / "cdk").is_dir():
        sys.exit("No AgentCore CLI project yet. Create it once, then run this again:\n"
                 f"    cd deploy\n    agentcore create --project-name {settings.PROJECT} --no-agent")
    policy = None
    if args.policy:
        state = provision.deployed(PROJECT_DIR)
        if "gateway_arn" not in state:
            sys.exit("The policies name the deployed gateway: run agentcore deploy once without --policy first.")
        if args.no_runtime:
            agents_role_arn = f"arn:aws:iam::{account(state['gateway_arn'])}:role/{settings.AGENTS_ROLE}"
        elif "runtime_role_arn" in state:
            agents_role_arn = state["runtime_role_arn"]
        else:
            sys.exit("The policies name the runtime's role: deploy the runtime once without --policy first, "
                     "or add --no-runtime.")
        policy = {"gateway_arn": state["gateway_arn"], "agents_role_arn": agents_role_arn,
                  "mode": MODES[args.policy]}

    agentcore.build(PROJECT_DIR, model_id, app_settings.REPO_ROOT, policy, with_runtime=not args.no_runtime)
    targets_path = PROJECT_DIR / "agentcore" / "aws-targets.json"
    existing = json.loads(targets_path.read_text(encoding="utf-8")) if targets_path.exists() else []
    if not any(target.get("name") == "default" for target in existing):
        account = boto3.Session(region_name=settings.REGION).client("sts").get_caller_identity()["Account"]
        targets_path.write_text(json.dumps(agentcore.deployment_targets(existing, account), indent=2) + "\n",
                                encoding="utf-8")
    shown = PROJECT_DIR.relative_to(app_settings.REPO_ROOT).as_posix()
    print(f"Wrote {shown}/agentcore/agentcore.json, {shown}/{agentcore.RUNTIME_DIR}, {shown}/{agentcore.TOOLS_DIR}")
    if policy:
        print(f"Cedar policies attached to the gateway in {policy['mode']} mode.")
    print(f"Next: cd {shown} && agentcore validate && agentcore deploy")


if __name__ == "__main__":
    main()
