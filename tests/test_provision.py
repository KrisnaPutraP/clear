"""Setup and cleanup of the AWS resources the AgentCore CLI does not manage (docs/PLAN.md §8d).
Every request is stubbed and checked against the real AWS API models; nothing reaches AWS."""

import json
from datetime import datetime, timezone

import boto3
import pytest
from botocore.stub import ANY, Stubber

from aws_fakes import SEED_DIR
from clear_aws import provision, settings

ACCOUNT = "123456789012"
SAP_KEY = {name: f"value of {name}" for name in settings.SAP_SETTINGS}
SAP_VALUE = json.dumps({name: SAP_KEY[name] for name in settings.SAP_SETTINGS})
TAGS = [{"Key": "Project", "Value": "ID-Hackathon-2026"}, {"Key": "Team", "Value": "Cookusan"},
        {"Key": "DeleteAfter", "Value": "2026-10-31"}]
NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
ROLES = (settings.ACTION_ROLE, settings.AGENTS_ROLE)


def role(name: str) -> dict:
    return {"Path": "/", "RoleName": name, "RoleId": "AROAEXAMPLE0000000000", "CreateDate": NOW,
            "Arn": f"arn:aws:iam::{ACCOUNT}:role/{name}"}


PROJECT_STACK = f"{settings.STACK_PREFIX}default"


class StubbedAws:
    """Clients by service name, each with a Stubber holding the requests a test expects."""

    def __init__(self):
        self.clients, self.stubbers = {}, {}

    def __call__(self, service: str):
        if service not in self.clients:
            session = boto3.session.Session(aws_access_key_id="test", aws_secret_access_key="test",
                                            region_name=settings.REGION)
            self.clients[service] = session.client(service)
            self.stubbers[service] = Stubber(self.clients[service])
            self.stubbers[service].activate()
        return self.clients[service]

    def expect(self, service: str, operation: str, params: dict, response: dict | None = None) -> None:
        self(service)
        self.stubbers[service].add_response(operation, response or {}, params)

    def refuse(self, service: str, operation: str, params: dict, code: str) -> None:
        self(service)
        self.stubbers[service].add_client_error(operation, service_error_code=code, expected_params=params)

    def verify(self) -> None:
        for stubber in self.stubbers.values():
            stubber.assert_no_pending_responses()


@pytest.fixture
def aws(monkeypatch, tmp_path):
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    stubbed = StubbedAws()
    yield stubbed
    stubbed.verify()


def stack(name: str, status: str = "CREATE_COMPLETE", outputs: list | None = None) -> dict:
    return {"StackName": name, "CreationTime": NOW, "StackStatus": status, "Outputs": outputs or []}


def expect_lookups(aws, table=False, roles=False, parameter: bool | None = False) -> None:
    """Stub the read-only lookups; parameter=None when the SSM parameter is not looked up."""
    if table:
        aws.expect("dynamodb", "describe_table", {"TableName": settings.TABLE}, {"Table": {"TableStatus": "ACTIVE"}})
    else:
        aws.refuse("dynamodb", "describe_table", {"TableName": settings.TABLE}, "ResourceNotFoundException")
    for name in ROLES:
        if roles:
            aws.expect("iam", "get_role", {"RoleName": name}, {"Role": role(name)})
        else:
            aws.refuse("iam", "get_role", {"RoleName": name}, "NoSuchEntity")
    if parameter:
        aws.expect("ssm", "get_parameter", {"Name": settings.SAP_PARAMETER},
                   {"Parameter": {"Name": settings.SAP_PARAMETER, "Type": "SecureString"}})
    elif parameter is False:
        aws.refuse("ssm", "get_parameter", {"Name": settings.SAP_PARAMETER}, "ParameterNotFound")


def test_setup_creates_what_is_missing_with_the_tags(aws):
    expect_lookups(aws)
    steps = provision.setup_steps(aws, ACCOUNT, SAP_KEY, SEED_DIR)
    files = sum(1 for path in SEED_DIR.rglob("*") if path.is_file())

    assert all(step.apply for step in steps)
    assert f"Load the {files} files" in steps[4].description

    aws.expect("dynamodb", "create_table", {
        "TableName": settings.TABLE, "AttributeDefinitions": [{"AttributeName": "name", "AttributeType": "S"}],
        "KeySchema": [{"AttributeName": "name", "KeyType": "HASH"}], "BillingMode": "PAY_PER_REQUEST", "Tags": TAGS})
    aws.expect("dynamodb", "describe_table", {"TableName": settings.TABLE}, {"Table": {"TableStatus": "ACTIVE"}})
    for name in ROLES:
        aws.expect("iam", "create_role", {"RoleName": name, "AssumeRolePolicyDocument": ANY,
                                          "Description": ANY, "Tags": TAGS}, {"Role": role(name)})
        aws.expect("iam", "put_role_policy", {"RoleName": name, "PolicyName": "invoke-gateway",
                                              "PolicyDocument": ANY})
    aws.expect("ssm", "put_parameter", {"Name": settings.SAP_PARAMETER, "Value": SAP_VALUE, "Type": "SecureString",
                                        "Description": ANY, "Tags": TAGS}, {"Version": 1})
    for step in steps[:4]:  # Loading the seed is reset_table, tested with the DynamoDB store.
        step.apply()


def test_setup_with_everything_in_place_refreshes_the_role_and_the_key(aws):
    expect_lookups(aws, table=True, roles=True, parameter=True)
    table, action_role, agents_role, parameter, _ = provision.setup_steps(aws, ACCOUNT, SAP_KEY, SEED_DIR)

    assert table.apply is None
    for name in ROLES:
        aws.expect("iam", "put_role_policy", {"RoleName": name, "PolicyName": "invoke-gateway",
                                              "PolicyDocument": ANY})
    aws.expect("ssm", "put_parameter", {"Name": settings.SAP_PARAMETER, "Value": SAP_VALUE, "Type": "SecureString",
                                        "Overwrite": True}, {"Version": 2})
    action_role.apply()
    agents_role.apply()
    parameter.apply()


def test_setup_without_the_sap_key_leaves_predictions_on_the_baseline(aws):
    expect_lookups(aws, table=True, roles=True, parameter=None)
    parameter = provision.setup_steps(aws, ACCOUNT, {}, SEED_DIR)[3]

    assert parameter.apply is None
    assert "baseline" in parameter.description


def test_the_action_role_trusts_its_own_account_and_may_only_invoke_gateways(aws):
    expect_lookups(aws)
    action_role = provision.setup_steps(aws, ACCOUNT, SAP_KEY, SEED_DIR)[1]
    sent = {}
    aws("iam").meta.events.register("before-parameter-build.iam.*",
                                    lambda params, model, **kwargs: sent.setdefault(model.name, dict(params)))
    aws.expect("iam", "create_role", {"RoleName": settings.ACTION_ROLE, "AssumeRolePolicyDocument": ANY,
                                      "Description": ANY, "Tags": TAGS}, {"Role": role(settings.ACTION_ROLE)})
    aws.expect("iam", "put_role_policy", {"RoleName": settings.ACTION_ROLE, "PolicyName": "invoke-gateway",
                                          "PolicyDocument": ANY})
    action_role.apply()

    trust = json.loads(sent["CreateRole"]["AssumeRolePolicyDocument"])
    assert trust["Statement"] == [{"Effect": "Allow", "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
                                   "Action": "sts:AssumeRole"}]
    policy = json.loads(sent["PutRolePolicy"]["PolicyDocument"])
    assert policy["Statement"] == [{"Effect": "Allow", "Action": "bedrock-agentcore:InvokeGateway",
                                    "Resource": f"arn:aws:bedrock-agentcore:us-west-2:{ACCOUNT}:gateway/*"}]


def test_cleanup_deletes_every_project_resource_in_order(aws):
    aws.expect("cloudformation", "describe_stacks", {}, {"Stacks": [stack(PROJECT_STACK), stack("SomeoneElse")]})
    expect_lookups(aws, table=True, roles=True, parameter=True)
    lambda_logs = f"/aws/lambda/{settings.PROJECT}-{settings.TARGET}"
    aws.expect("logs", "describe_log_groups", {"logGroupNamePrefix": provision.LOG_GROUP_PREFIXES[0]},
               {"logGroups": [{"logGroupName": lambda_logs}]})
    aws.expect("logs", "describe_log_groups", {"logGroupNamePrefix": provision.LOG_GROUP_PREFIXES[1]},
               {"logGroups": []})
    steps = provision.cleanup_steps(aws)

    assert [s.description.split(" ")[1] for s in steps] == ["CloudFormation", "DynamoDB", "IAM", "IAM", "SSM", "log"]

    aws.expect("cloudformation", "delete_stack", {"StackName": PROJECT_STACK})
    aws.expect("cloudformation", "describe_stacks", {"StackName": PROJECT_STACK},
               {"Stacks": [stack(PROJECT_STACK, "DELETE_COMPLETE")]})
    aws.expect("dynamodb", "delete_table", {"TableName": settings.TABLE})
    aws.refuse("dynamodb", "describe_table", {"TableName": settings.TABLE}, "ResourceNotFoundException")
    for name in ROLES:
        aws.expect("iam", "list_role_policies", {"RoleName": name}, {"PolicyNames": ["invoke-gateway"]})
        aws.expect("iam", "delete_role_policy", {"RoleName": name, "PolicyName": "invoke-gateway"})
        aws.expect("iam", "list_attached_role_policies", {"RoleName": name}, {"AttachedPolicies": []})
        aws.expect("iam", "delete_role", {"RoleName": name})
    aws.expect("ssm", "delete_parameter", {"Name": settings.SAP_PARAMETER})
    aws.expect("logs", "delete_log_group", {"logGroupName": lambda_logs})
    for step in steps:
        step.apply()


def test_cleanup_with_nothing_left_says_so(aws):
    aws.expect("cloudformation", "describe_stacks", {}, {"Stacks": []})
    expect_lookups(aws)
    for prefix in provision.LOG_GROUP_PREFIXES:
        aws.expect("logs", "describe_log_groups", {"logGroupNamePrefix": prefix}, {"logGroups": []})

    assert [step.description for step in provision.cleanup_steps(aws)] == ["Nothing to delete"]


def test_cleanup_of_the_cdk_bootstrap_empties_its_bucket_and_repository(aws):
    aws.expect("cloudformation", "describe_stacks", {}, {"Stacks": []})
    expect_lookups(aws)
    for prefix in provision.LOG_GROUP_PREFIXES:
        aws.expect("logs", "describe_log_groups", {"logGroupNamePrefix": prefix}, {"logGroups": []})
    bucket = f"cdk-hnb659fds-assets-{ACCOUNT}-us-west-2"
    repository = f"cdk-hnb659fds-container-assets-{ACCOUNT}-us-west-2"
    outputs = [{"OutputKey": "BucketName", "OutputValue": bucket},
               {"OutputKey": "ImageRepositoryName", "OutputValue": repository}]
    aws.expect("cloudformation", "describe_stacks", {"StackName": "CDKToolkit"},
               {"Stacks": [stack("CDKToolkit", outputs=outputs)]})
    steps = provision.cleanup_steps(aws, include_bootstrap=True)

    assert len(steps) == 3
    aws.expect("cloudformation", "delete_stack", {"StackName": "CDKToolkit"})
    aws.expect("cloudformation", "describe_stacks", {"StackName": "CDKToolkit"},
               {"Stacks": [stack("CDKToolkit", "DELETE_COMPLETE")]})
    aws.expect("s3", "list_object_versions", {"Bucket": bucket}, {
        "Versions": [{"Key": "runtime.zip", "VersionId": "v1"}],
        "DeleteMarkers": [{"Key": "tools.zip", "VersionId": "v2"}]})
    aws.expect("s3", "delete_objects", {"Bucket": bucket, "Delete": {"Objects": [
        {"Key": "runtime.zip", "VersionId": "v1"}, {"Key": "tools.zip", "VersionId": "v2"}], "Quiet": True}})
    aws.expect("s3", "delete_bucket", {"Bucket": bucket})
    aws.expect("ecr", "delete_repository", {"repositoryName": repository, "force": True})
    for step in steps:
        step.apply()


def test_dry_run_changes_nothing(capsys):
    applied = []
    provision.run([provision.Step("exists"), provision.Step("create", lambda: applied.append(1))], apply=False)

    assert applied == []
    assert "Dry run: nothing changed" in capsys.readouterr().out


def test_deployed_arns_come_from_the_cli_state(tmp_path):
    assert provision.deployed(tmp_path) == {}
    state = tmp_path / "agentcore" / ".cli" / "deployed-state.json"
    state.parent.mkdir(parents=True)
    runtime = f"arn:aws:bedrock-agentcore:us-west-2:{ACCOUNT}:runtime/{settings.PROJECT}_clear-AbCdEf1234"
    role = f"arn:aws:iam::{ACCOUNT}:role/AgentCore-{settings.PROJECT}-RuntimeRole-XYZ"
    gateway = f"arn:aws:bedrock-agentcore:us-west-2:{ACCOUNT}:gateway/{settings.PROJECT}-tools-abc123"
    url = "https://abc123.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp"
    state.write_text(json.dumps({"targets": {"default": {"resources": {
        "runtimes": {settings.RUNTIME: {"runtimeId": "x", "runtimeArn": runtime, "roleArn": role}},
        "mcp": {"gateways": {settings.GATEWAY: {"gatewayId": "abc123", "gatewayArn": gateway, "gatewayUrl": url}}},
    }}}}), encoding="utf-8")

    assert provision.deployed(tmp_path) == {"runtime_arn": runtime, "runtime_role_arn": role, "gateway_arn": gateway,
                                          "gateway_url": url}


def test_the_gateway_url_is_found_by_the_projects_gateway_name(aws):
    name = f"{settings.PROJECT}-{settings.GATEWAY}"
    url = f"https://{name}-abc123.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp"

    def gateway(gateway_name: str) -> dict:
        return {"gatewayId": f"{gateway_name}-abc123", "name": gateway_name, "status": "READY", "createdAt": NOW,
                "updatedAt": NOW, "authorizerType": "AWS_IAM"}

    aws.expect("bedrock-agentcore-control", "list_gateways", {},
               {"items": [gateway("someone-elses"), gateway(name)]})
    aws.expect("bedrock-agentcore-control", "get_gateway", {"gatewayIdentifier": f"{name}-abc123"},
               {**gateway(name), "gatewayArn": f"arn:aws:bedrock-agentcore:us-west-2:{ACCOUNT}:gateway/{name}-abc123",
                "gatewayUrl": url})
    assert provision.gateway_url(aws("bedrock-agentcore-control")) == url

    aws.expect("bedrock-agentcore-control", "list_gateways", {}, {"items": []})
    assert provision.gateway_url(aws("bedrock-agentcore-control")) is None
