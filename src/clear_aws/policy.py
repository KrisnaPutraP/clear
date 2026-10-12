"""The Cedar policies on AgentCore Gateway (docs/PLAN.md §6a).

Company rules enforced outside the agents, so no prompt can talk an agent
past them. The gateway denies every tool call that no policy permits, and a
forbid always wins over a permit:

- The role the Evidence and Impact agents sign with (the runtime's own role,
  or the agents role when they run outside the runtime) may call the read
  and assessment tools.
- The Action agent's role may call validate_action, the STO write, and
  get_inventory to verify stock.
- create_stock_transport_order is forbidden unless the caller is the Action
  agent's role and the call carries an approval ID. As a forbid, it holds
  whatever other policies are added later.

clear_tools.sto still checks the approval record itself; the policy is the
outer layer. Naming specific tools requires the gateway's ARN, so the
policies are built from the CLI's state after a first deploy without them
(docs/deployment.md).
"""

from clear_aws import settings

ENGINE = "clear_policies"
AGENT_TOOLS = ("get_shipment", "get_purchase_order", "get_documents", "get_inventory", "reconcile_documents",
               "predict_resolution_time", "calculate_supply_risk")
ACTION_TOOLS = ("validate_action", "create_stock_transport_order", "get_inventory")
WRITE_TOOL = "create_stock_transport_order"
APPROVAL_PATTERN = "APR-*"  # IDs from clear_tools.records.


def engine(gateway_arn: str, agents_role_arn: str) -> dict:
    """The policy engine entry of agentcore.json, for the deployed gateway and the agents' role."""
    action_role = f"arn:aws:sts::{account(gateway_arn)}:assumed-role/{settings.ACTION_ROLE}"
    return {
        "name": ENGINE,
        "description": "CLEAR: which agent may call which tool, and the STO write only with approval",
        "tags": dict(settings.TAGS),
        "policies": [
            {"name": "agents_read_and_assess",
             "description": "Evidence and Impact agents: read and assessment tools",
             "statement": _permit(assumed_role(agents_role_arn), AGENT_TOOLS, gateway_arn)},
            {"name": "action_agent_tools",
             "description": "Action agent: validation, the STO write, and stock verification",
             "statement": _permit(action_role, ACTION_TOOLS, gateway_arn)},
            {"name": "sto_needs_action_agent_and_approval",
             "description": "No STO unless the Action agent calls with an approval ID",
             "statement": _forbid_write_without_approval(action_role, gateway_arn)},
        ],
    }


def assumed_role(role_arn: str) -> str:
    """The gateway's principal ID for a role's sessions: the assumed-role ARN without a session name."""
    _, _, _, _, account_id, resource = role_arn.split(":", 5)
    return f"arn:aws:sts::{account_id}:assumed-role/{resource.rsplit('/', 1)[-1]}"


def account(arn: str) -> str:
    return arn.split(":")[4]


def action(tool: str) -> str:
    return f'AgentCore::Action::"{settings.TARGET}{settings.TOOL_SEPARATOR}{tool}"'


def _permit(principal_id: str, tools: tuple[str, ...], gateway_arn: str) -> str:
    actions = ",\n    ".join(action(tool) for tool in tools)
    return (f"permit(\n"
            f"  principal is AgentCore::IamEntity,\n"
            f"  action in [\n    {actions}\n  ],\n"
            f'  resource == AgentCore::Gateway::"{gateway_arn}"\n'
            f")\n"
            f'when {{ principal.id == "{principal_id}" }};')


def _forbid_write_without_approval(action_role: str, gateway_arn: str) -> str:
    return (f"forbid(\n"
            f"  principal,\n"
            f"  action == {action(WRITE_TOOL)},\n"
            f'  resource == AgentCore::Gateway::"{gateway_arn}"\n'
            f")\n"
            f"unless {{\n"
            f"  principal is AgentCore::IamEntity &&\n"
            f'  principal.id == "{action_role}" &&\n'
            f'  context.input.approval_id like "{APPROVAL_PATTERN}"\n'
            f"}};")
