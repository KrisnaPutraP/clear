"""Assemble the AgentCore CLI project for deployment (docs/deployment.md).

Writes agentcore.json, the runtime's code location (agents), and the Lambda
function's code location (tools) into deploy/cookusanhackathon/, the project
directory that `agentcore create` made. Local files only: nothing reaches
AWS until you run `agentcore deploy` in that directory.

Usage:
    python scripts/build_deploy.py
"""

import os
import sys

from clear_app import settings as app_settings
from clear_aws import agentcore, settings

PROJECT_DIR = app_settings.REPO_ROOT / "deploy" / settings.PROJECT


def main() -> None:
    app_settings.load_env()
    model_id = os.environ.get("CLEAR_BEDROCK_MODEL_ID")
    if not model_id:
        sys.exit("Set CLEAR_BEDROCK_MODEL_ID in .env first: the runtime's agents need it.")
    if not (PROJECT_DIR / "agentcore" / "cdk").is_dir():
        sys.exit("No AgentCore CLI project yet. Create it once, then run this again:\n"
                 f"    cd deploy\n    agentcore create --project-name {settings.PROJECT} --no-agent")
    agentcore.build(PROJECT_DIR, model_id, app_settings.REPO_ROOT)
    shown = PROJECT_DIR.relative_to(app_settings.REPO_ROOT).as_posix()
    print(f"Wrote {shown}/agentcore/agentcore.json, {shown}/{agentcore.RUNTIME_DIR}, {shown}/{agentcore.TOOLS_DIR}")
    print(f"Next: cd {shown} && agentcore validate && agentcore deploy")


if __name__ == "__main__":
    main()
