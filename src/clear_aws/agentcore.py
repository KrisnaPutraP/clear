"""The AgentCore CLI project (docs/PLAN.md §2c, §5b, §8d).

- One runtime runs the orchestrator and the three specialists in one process
  (CodeZip, Python 3.12). The CLI grants it Bedrock and the gateway and sets
  the gateway URL; its policy file adds the DynamoDB table and the Action
  agent's role.
- One gateway, authorized with AWS IAM, in front of one Lambda target that
  runs all nine tools. The target's tool definitions come from the agents'
  Strands tools, reduced to what a gateway schema can say: each argument's
  type and description, and which are required. The full schemas stay with
  the agents, because their tools run locally and only the calls travel
  (clear_aws.gateway).
- With policy settings, a Cedar policy engine on the gateway (clear_aws.policy),
  in LOG_ONLY mode to observe decisions or ENFORCE to apply them.

build() writes agentcore.json and both code locations into the project
directory that `agentcore create` made (docs/deployment.md).
"""

import json
import shutil
from pathlib import Path

from clear_agents import tools
from clear_aws import policy as cedar
from clear_aws import settings

SCHEMA = "https://schema.agentcore.aws.dev/v1/agentcore.json"
PYTHON = "PYTHON_3_12"
RUNTIME_DIR = f"app/{settings.RUNTIME}"  # Code locations, relative to the CLI project directory.
TOOLS_DIR = f"app/{settings.TARGET}"
RUNTIME_POLICY = "runtime-policy.json"  # In the runtime's code location.
LAMBDA_TIMEOUT_SECONDS = 60
TABLE_ARN = f"arn:aws:dynamodb:{settings.REGION}:*:table/{settings.TABLE}"
GATEWAY_TYPES = {"string", "number", "integer", "boolean", "object", "array"}

# Code location -> (template directory under deploy/, packages and modules copied from src/).
BUNDLES = {
    RUNTIME_DIR: ("runtime", {"clear_tools": None, "clear_agents": None, "clear_aws": None}),
    TOOLS_DIR: ("tools", {"clear_tools": None,
                          "clear_aws": ["__init__.py", "settings.py", "dynamo_store.py", "lambda_tools.py"]}),
}


def project(model_id: str, policy: dict | None = None) -> dict:
    """agentcore.json for agents on the Bedrock model model_id.

    policy, if given, holds gateway_arn and runtime_role_arn of the deployed project and the mode,
    LOG_ONLY or ENFORCE, in which the gateway applies the Cedar policies.
    """
    spec = {
        "$schema": SCHEMA,
        "name": settings.PROJECT,
        "version": 1,
        "managedBy": "CDK",
        "tags": dict(settings.TAGS),
        "runtimes": [runtime(model_id)],
        "agentCoreGateways": [gateway(policy["mode"] if policy else None)],
    }
    if policy:
        spec["policyEngines"] = [cedar.engine(policy["gateway_arn"], policy["runtime_role_arn"])]
    return spec


def runtime(model_id: str) -> dict:
    return {
        "name": settings.RUNTIME,
        "description": "CLEAR orchestrator and specialist agents",
        "build": "CodeZip",
        "entrypoint": "main.py",
        "codeLocation": RUNTIME_DIR,
        "runtimeVersion": PYTHON,
        "protocol": "HTTP",
        "networkMode": "PUBLIC",
        "instrumentation": {"enableOtel": True},
        "envVars": [
            {"name": "CLEAR_BEDROCK_MODEL_ID", "value": model_id},
            {"name": settings.TABLE_SETTING, "value": settings.TABLE},
            {"name": settings.ACTION_ROLE_SETTING, "value": settings.ACTION_ROLE},
        ],
        "additionalPolicies": [RUNTIME_POLICY],
        "tags": dict(settings.TAGS),
    }


def gateway(policy_mode: str | None = None) -> dict:
    spec = {
        "name": settings.GATEWAY,
        "description": "CLEAR tools: mock S/4HANA, documents, prediction, supply risk, validation, STO",
        "protocolType": "MCP",
        "authorizerType": "AWS_IAM",
        "enableSemanticSearch": False,
        "exceptionLevel": "DEBUG",  # Gateway errors explain themselves; the tools return their own.
        "tags": dict(settings.TAGS),
        "targets": [{
            "name": settings.TARGET,
            "targetType": "lambda",
            "toolDefinitions": tool_definitions(),
            "compute": {
                "host": "Lambda",
                "implementation": {"language": "Python", "path": TOOLS_DIR, "handler": "handler.lambda_handler"},
                "pythonVersion": PYTHON,
                "timeout": LAMBDA_TIMEOUT_SECONDS,
                "memorySize": 512,
                "iamPolicy": lambda_policy(),
            },
        }],
    }
    if policy_mode:
        spec["policyEngineConfiguration"] = {"policyEngineName": cedar.ENGINE, "mode": policy_mode}
    return spec


def deployment_targets(existing: list[dict], account: str) -> list[dict]:
    """aws-targets.json with a "default" target in the deployment region; the CLI names the stack after it."""
    if any(target.get("name") == "default" for target in existing):
        return existing
    return existing + [{"name": "default", "description": "CLEAR hackathon deployment", "account": account,
                        "region": settings.REGION}]


def runtime_policy() -> dict:
    """What the runtime needs beyond the CLI's grants: the case log and records, and the Action agent's role."""
    return _policy(
        {"Sid": "ClearData", "Action": ["dynamodb:GetItem", "dynamodb:UpdateItem"], "Resource": TABLE_ARN},
        {"Sid": "ActionAgentRole", "Action": "sts:AssumeRole",
         "Resource": f"arn:aws:iam::*:role/{settings.ACTION_ROLE}"},
    )


def lambda_policy() -> dict:
    """The tools' data and the SAP AI Core key."""
    return _policy(
        {"Sid": "ClearData", "Action": ["dynamodb:GetItem", "dynamodb:UpdateItem"], "Resource": TABLE_ARN},
        {"Sid": "SapAiCoreKey", "Action": "ssm:GetParameter",
         "Resource": f"arn:aws:ssm:{settings.REGION}:*:parameter{settings.SAP_PARAMETER}"},
    )


def tool_definitions() -> list[dict]:
    """Gateway tool definitions of the nine tools, from the agents' Strands tools."""
    def unused(name: str, arguments: dict) -> dict:  # Building tools needs an Invoke; definitions never call it.
        raise AssertionError(name)

    agent_tools = tools.evidence_tools(unused) + tools.impact_tools(unused) + tools.action_tools(unused)
    specs = {tool.tool_spec["name"]: tool.tool_spec for tool in agent_tools}  # get_inventory is listed twice.
    return [{"name": name, "description": spec["description"],
             "inputSchema": _input_schema(spec["inputSchema"]["json"])} for name, spec in specs.items()]


def build(project_dir: Path, model_id: str, repo_root: Path, policy: dict | None = None) -> None:
    """Write agentcore.json and both code locations into the CLI project directory."""
    for location, (template, packages) in BUNDLES.items():
        target = project_dir / location
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(repo_root / "deploy" / template, target)
        for package, modules in packages.items():
            source = repo_root / "src" / package
            if modules is None:
                shutil.copytree(source, target / package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                (target / package).mkdir()
                for module in modules:
                    shutil.copy2(source / module, target / package / module)
    _write_json(project_dir / RUNTIME_DIR / RUNTIME_POLICY, runtime_policy())
    _write_json(project_dir / "agentcore" / "agentcore.json", project(model_id, policy))


def _input_schema(schema: dict) -> dict:
    reduced = {"type": "object", "properties": {name: _argument(name, spec)
                                                for name, spec in schema.get("properties", {}).items()}}
    if schema.get("required"):
        reduced["required"] = list(schema["required"])
    return reduced


def _argument(name: str, spec: dict) -> dict:
    """One argument as type and description. Nested structure is left out; the gateway only routes."""
    options = [option for option in spec.get("anyOf", [spec]) if option.get("type") != "null"]
    kinds = {option.get("type") for option in options}
    if len(kinds) != 1 or not kinds <= GATEWAY_TYPES:
        raise ValueError(f"Argument {name} needs a single gateway type, has {sorted(map(str, kinds))}")
    [kind] = kinds
    argument = {"type": kind}
    if spec.get("description"):
        argument["description"] = spec["description"]
    if kind == "array":
        argument["items"] = {"type": options[0].get("items", {}).get("type", "object")}
    return argument


def _policy(*statements: dict) -> dict:
    return {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", **statement} for statement in statements]}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
