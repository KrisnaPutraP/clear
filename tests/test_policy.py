"""The Cedar policies on AgentCore Gateway (docs/PLAN.md §6a): they grant each agent's IAM role exactly
the tools that agent holds in code, and forbid the STO write without the Action agent and an approval."""

import re

from clear_agents import tools
from clear_aws import agentcore, policy, settings

ACCOUNT = "123456789012"
GATEWAY = f"arn:aws:bedrock-agentcore:us-west-2:{ACCOUNT}:gateway/{settings.PROJECT}-tools-abc123"
RUNTIME_ROLE = f"arn:aws:iam::{ACCOUNT}:role/service-role/AgentCore-{settings.PROJECT}-RuntimeRole-XYZ"
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,47}")  # The CLI's rule for policy engine and policy names.


def names(agent_tools: list) -> set[str]:
    return {tool.tool_spec["name"] for tool in agent_tools}


def unused(name, arguments):
    raise AssertionError(name)


def test_each_role_gets_exactly_the_tools_its_agents_hold():
    readers = names(tools.evidence_tools(unused) + tools.impact_tools(unused))

    assert set(policy.AGENT_TOOLS) == readers
    assert set(policy.ACTION_TOOLS) == names(tools.action_tools(unused))
    assert policy.WRITE_TOOL not in readers


def test_policies_name_the_deployed_gateway_and_roles():
    engine = policy.engine(GATEWAY, RUNTIME_ROLE)
    statements = {p["name"]: p["statement"] for p in engine["policies"]}
    action_role = f'"arn:aws:sts::{ACCOUNT}:assumed-role/{settings.ACTION_ROLE}"'

    assert all(f'resource == AgentCore::Gateway::"{GATEWAY}"' in s for s in statements.values())
    assert f'"arn:aws:sts::{ACCOUNT}:assumed-role/AgentCore-{settings.PROJECT}-RuntimeRole-XYZ"' \
        in statements["agents_read_and_assess"]
    assert action_role in statements["action_agent_tools"]
    write = statements["sto_needs_action_agent_and_approval"]
    assert write.startswith("forbid(")
    assert f'action == AgentCore::Action::"{settings.TARGET}___create_stock_transport_order"' in write
    assert action_role in write
    assert 'context.input.approval_id like "APR-*"' in write


def test_names_fit_the_cli_rules():
    engine = policy.engine(GATEWAY, RUNTIME_ROLE)

    assert NAME.fullmatch(engine["name"])
    assert all(NAME.fullmatch(p["name"]) and len(p["description"]) <= 4096 for p in engine["policies"])
    assert engine["tags"] == settings.TAGS


def test_policies_attach_only_when_asked():
    plain = agentcore.project("model-x")
    attached = agentcore.project("model-x", {"gateway_arn": GATEWAY, "runtime_role_arn": RUNTIME_ROLE,
                                             "mode": "LOG_ONLY"})

    assert "policyEngines" not in plain
    assert "policyEngineConfiguration" not in plain["agentCoreGateways"][0]
    assert attached["agentCoreGateways"][0]["policyEngineConfiguration"] == {
        "policyEngineName": policy.ENGINE, "mode": "LOG_ONLY"}
    assert [e["name"] for e in attached["policyEngines"]] == [policy.ENGINE]
