"""Check what the Cedar policies on the deployed gateway allow and deny (docs/deployment.md).

Calls the gateway as each caller the policies name, and as an administrator
without either role, and compares every outcome with the rule it should
follow. No call can write: each one names a shipment, prediction, or
validation that does not exist where a wrong allow would reach a tool that
writes, so the tool refuses on its own.

Run it after every change to the policies. AgentCore does not check the STO
forbid when it is deployed (src/clear_aws/policy.py), so this is its check.

Usage:
    python scripts/check_policies.py
"""

import logging
import os
import sys

from clear_app import settings as app_settings
from clear_aws import gateway, settings

ROLES = {"action_role": settings.ACTION_ROLE, "agents_role": settings.AGENTS_ROLE}
NO_ROLE: dict = {}

# Caller, its roles, the agent whose session is used, tool, arguments, expected outcome.
CASES = [
    ("Agents role", ROLES, "evidence", "get_shipment", {"shipment_id": "SHP-1001"}, "allowed"),
    ("Agents role", ROLES, "evidence", "validate_action",
     {"shipment_id": "SHP-1001", "prediction_id": "PRED-9999", "source_plant": "1200", "quantity_t": 1}, "denied"),
    ("Action role", ROLES, "action", "create_stock_transport_order",
     {"validation_id": "VAL-9999", "approval_id": "X-1"}, "denied"),
    ("Action role", ROLES, "action", "create_stock_transport_order",
     {"validation_id": "VAL-9999", "approval_id": "APR-9999"}, "allowed"),
    ("Action role", ROLES, "action", "predict_resolution_time", {"shipment_id": "SHP-9999"}, "denied"),
    ("Administrator, no role", NO_ROLE, "evidence", "get_shipment", {"shipment_id": "SHP-1001"}, "denied"),
]


def main() -> None:
    app_settings.load_env()
    url = os.environ.get(settings.GATEWAY_URL_SETTING)
    if not url:
        sys.exit(f"Set {settings.GATEWAY_URL_SETTING} in .env first (python scripts/aws_setup.py prints it).")
    logging.getLogger("strands").setLevel(logging.CRITICAL)  # A denied call is expected here, not an error.

    wrong = 0
    for caller, roles, agent, tool, arguments, expected in CASES:
        got, detail = call(url, roles, agent, tool, arguments)
        wrong += got != expected
        mark = "ok   " if got == expected else "WRONG"
        print(f"{mark} {caller:<23} {tool:<29} {arguments.get('approval_id', ''):<9} {got:<8} {detail}")
    if wrong:
        sys.exit(f"{wrong} of {len(CASES)} calls did not follow the policies.")
    print(f"All {len(CASES)} calls follow the policies.")


def call(url: str, roles: dict, agent: str, tool: str, arguments: dict) -> tuple[str, str]:
    """'denied' when the gateway's policies refused the call, else 'allowed', with what came back."""
    with gateway.Gateway(url, roles.get("action_role"), agents_role=roles.get("agents_role")) as invoke_for:
        try:
            invoke_for(agent)(tool, arguments)
        except gateway.GatewayError as error:
            if "policy enforcement" in str(error):
                return "denied", str(error).rsplit("[", 1)[-1].rstrip("]")[:60]
            raise
        except Exception as error:  # The policies let the call through; the tool itself refused it.
            return "allowed", f"the tool refused: {type(error).__name__}: {str(error)[:50]}"
    return "allowed", "the tool answered"


if __name__ == "__main__":
    main()
