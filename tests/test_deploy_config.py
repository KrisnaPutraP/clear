"""The AgentCore CLI project and its code bundles (docs/PLAN.md §2c, §5b, §8d), checked against the
rules of the CLI's own schema, without running the CLI."""

import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from clear_aws import agentcore, settings
from clear_tools import catalog

REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SCHEMA_KEYS = {"type", "description", "properties", "required", "items"}
# boto3 and its dependencies, all in the Lambda Python runtime; botocore uses certifi and awscrt when present.
LAMBDA_PROVIDED = {"boto3", "botocore", "jmespath", "dateutil", "urllib3", "s3transfer", "six", "certifi", "awscrt"}


@pytest.fixture(scope="module")
def project():
    return agentcore.project("us.anthropic.example-model-v1:0")


def test_names_fit_the_cli_rules_and_resources_carry_the_tags(project):
    assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,22}", project["name"])
    [runtime] = project["runtimes"]
    assert re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,47}", f"{project['name']}_{runtime['name']}")
    [gateway] = project["agentCoreGateways"]
    assert re.fullmatch(r"[0-9a-zA-Z](?:[0-9a-zA-Z-]*[0-9a-zA-Z])?", gateway["name"])
    assert settings.GATEWAY_URL_SETTING == f"AGENTCORE_GATEWAY_{gateway['name'].upper().replace('-', '_')}_URL"
    for resource in (project, runtime, gateway):
        assert resource["tags"] == {"Project": "ID-Hackathon-2026", "Team": "Cookusan", "DeleteAfter": "2026-10-31"}


def test_gateway_is_iam_authorized_and_lists_every_tool_in_its_schema_subset(project):
    [gateway] = project["agentCoreGateways"]
    [target] = gateway["targets"]

    assert gateway["authorizerType"] == "AWS_IAM"
    assert "_" not in target["name"]  # The gateway joins target and tool with "___".
    assert [d["name"] for d in target["toolDefinitions"]] == list(catalog.TOOLS)

    def check(node: dict) -> None:
        assert set(node) <= GATEWAY_SCHEMA_KEYS
        assert node["type"] in agentcore.GATEWAY_TYPES
        for child in node.get("properties", {}).values():
            check(child)
        if "items" in node:
            check(node["items"])

    for definition in target["toolDefinitions"]:
        assert definition["description"]
        check(definition["inputSchema"])
        assert set(definition["inputSchema"].get("required", [])) <= set(definition["inputSchema"]["properties"])


def test_runtime_settings_match_what_the_code_reads(project):
    [runtime] = project["runtimes"]
    env = {variable["name"]: variable["value"] for variable in runtime["envVars"]}

    assert env == {"CLEAR_BEDROCK_MODEL_ID": "us.anthropic.example-model-v1:0",
                   settings.TABLE_SETTING: settings.TABLE, settings.ACTION_ROLE_SETTING: settings.ACTION_ROLE}
    assert runtime["entrypoint"] == "main.py"
    assert (REPO_ROOT / "deploy" / "runtime" / "main.py").is_file()
    handler = project["agentCoreGateways"][0]["targets"][0]["compute"]["implementation"]["handler"]
    assert (REPO_ROOT / "deploy" / "tools" / f"{handler.split('.')[0]}.py").is_file()


def test_policies_grant_only_what_the_code_uses():
    runtime_actions = {s["Sid"]: s["Action"] for s in agentcore.runtime_policy()["Statement"]}
    lambda_actions = {s["Sid"]: s["Action"] for s in agentcore.lambda_policy()["Statement"]}

    assert runtime_actions == {"ClearData": ["dynamodb:GetItem", "dynamodb:UpdateItem"],
                               "ActionAgentRole": "sts:AssumeRole"}
    assert lambda_actions == {"ClearData": ["dynamodb:GetItem", "dynamodb:UpdateItem"],
                              "SapAiCoreKey": "ssm:GetParameter"}


def test_runtime_bundle_pins_the_strands_version_the_tests_run():
    pyproject = tomllib.loads((REPO_ROOT / "deploy" / "runtime" / "pyproject.toml").read_text(encoding="utf-8"))
    pins = dict(requirement.split("==") for requirement in pyproject["project"]["dependencies"])

    assert pins["strands-agents"] == importlib.metadata.version("strands-agents")
    assert {"bedrock-agentcore", "mcp-proxy-for-aws", "aws-opentelemetry-distro"} <= set(pins)


def test_build_writes_the_config_and_both_bundles(tmp_path):
    agentcore.build(tmp_path, "model-x", REPO_ROOT)

    written = json.loads((tmp_path / "agentcore" / "agentcore.json").read_text(encoding="utf-8"))
    assert written == agentcore.project("model-x")
    runtime_dir, tools_dir = tmp_path / agentcore.RUNTIME_DIR, tmp_path / agentcore.TOOLS_DIR
    assert json.loads((runtime_dir / agentcore.RUNTIME_POLICY).read_text()) == agentcore.runtime_policy()
    assert {p.name for p in runtime_dir.iterdir()} >= {"main.py", "pyproject.toml", "clear_tools", "clear_agents",
                                                        "clear_aws"}
    assert sorted(p.name for p in (tools_dir / "clear_aws").iterdir()) == [
        "__init__.py", "dynamo_store.py", "lambda_tools.py", "settings.py"]
    assert not list(tmp_path.rglob("__pycache__"))


def test_lambda_bundle_imports_only_what_the_lambda_runtime_provides(tmp_path):
    agentcore.build(tmp_path, "model-x", REPO_ROOT)
    bundle = tmp_path / agentcore.TOOLS_DIR
    probe = (
        "import json, sys\n"
        "before = set(sys.modules)\n"
        "import handler, clear_aws.lambda_tools as module\n"
        "print(json.dumps({'file': module.__file__,\n"
        "                  'loaded': sorted({n.split('.')[0] for n in set(sys.modules) - before})}))\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd=bundle,
                            env={**os.environ, "PYTHONPATH": str(bundle)})
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)

    assert Path(report["file"]).resolve().is_relative_to(bundle.resolve())
    public = {name for name in report["loaded"] if not name.startswith("_")}  # Interpreter internals start with _.
    third_party = public - set(sys.stdlib_module_names) - {"handler", "clear_aws", "clear_tools"}
    assert third_party <= LAMBDA_PROVIDED, sorted(third_party - LAMBDA_PROVIDED)


def test_deployment_target_is_filled_once():
    filled = agentcore.deployment_targets([], "123456789012")

    assert filled == [{"name": "default", "description": "CLEAR hackathon deployment", "account": "123456789012",
                       "region": "us-west-2"}]
    assert agentcore.deployment_targets(filled, "999999999999") == filled


def test_project_without_the_runtime_keeps_the_gateway():
    without = agentcore.project("model-x", with_runtime=False)

    assert without["runtimes"] == []
    assert without["agentCoreGateways"] == agentcore.project("model-x")["agentCoreGateways"]
