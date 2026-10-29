"""Set the settings of the Joule A2A app on Cloud Foundry from .env.

Copies the SAP AI Core key, the model and prediction settings, and the Basic
credentials of the BTP destination to the app with `cf set-env`. With
--gateway it also asks for the access key of the app's own IAM user,
without echoing it, and sets it with the gateway URL and the two agent
roles, so the app's agents call their tools through
AgentCore Gateway on the DynamoDB table. Prints names, never values. Needs
`cf login` and `cf target` on the team space first; run `cf restart` after.

Usage:
    python scripts/cf_env.py
    python scripts/cf_env.py --gateway
"""

import argparse
import getpass
import os
import subprocess

from clear_app import settings

APP = "cookusan-clear-a2a"
URL = f"https://{APP}.cfapps.ap10.hana.ondemand.com/"
FROM_ENV = ["CLEAR_LLM_BACKEND", "SAP_AICORE_AUTH_URL", "SAP_AICORE_CLIENT_ID", "SAP_AICORE_CLIENT_SECRET",
            "SAP_AICORE_API_URL", "SAP_AICORE_RESOURCE_GROUP", "SAP_RPT_DEPLOYMENT_ID", "SAP_LLM_DEPLOYMENT_ID",
            "CLEAR_PREDICTION_BACKEND", "CLEAR_RPT_TIMEOUT_SECONDS", "CLEAR_A2A_USER", "CLEAR_A2A_PASSWORD"]
GATEWAY_FROM_ENV = ["AGENTCORE_GATEWAY_TOOLS_URL", "CLEAR_ACTION_ROLE", "CLEAR_AGENTS_ROLE"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gateway", action="store_true",
                        help="also set the IAM user's access key and the gateway settings")
    args = parser.parse_args()

    settings.load_env()
    values = {name: os.environ.get(name, "") for name in FROM_ENV} | {"CLEAR_A2A_URL": URL}
    if args.gateway:
        values |= {name: os.environ.get(name, "") for name in GATEWAY_FROM_ENV}
        values["AWS_DEFAULT_REGION"] = "us-west-2"
        values["AWS_ACCESS_KEY_ID"] = input("Access key ID of the app's IAM user: ").strip()
        values["AWS_SECRET_ACCESS_KEY"] = getpass.getpass("Secret access key (hidden): ").strip()
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SystemExit(f"Empty in .env or input: {', '.join(missing)}. Nothing was set.")
    for name, value in values.items():
        result = subprocess.run(["cf", "set-env", APP, name, value], capture_output=True, text=True)
        print(f"{name}: {'OK' if result.returncode == 0 else 'FAILED'}")
    print(f"Now run: cf restart {APP}")


if __name__ == "__main__":
    main()
