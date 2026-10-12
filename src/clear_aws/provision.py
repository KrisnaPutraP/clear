"""Resources the AgentCore CLI does not create, and the cleanup of everything (docs/PLAN.md §8d).

setup_steps() covers the DynamoDB table, the Action agent's IAM role, the
SSM parameter holding the SAP AI Core key, and the seed data. cleanup_steps()
covers the CLI's CloudFormation stack, those resources, the log groups, and
optionally the CDK bootstrap stack. Both look first, with read-only calls,
and return steps; scripts/aws_setup.py and scripts/aws_cleanup.py print the
steps and apply them only when asked.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from botocore.exceptions import ClientError

from clear_aws import settings
from clear_aws.dynamo_store import KEY, DynamoStore, reset_table

Clients = Callable[[str], object]  # Service name -> boto3 client in the deployment region.
TAG_LIST = [{"Key": key, "Value": value} for key, value in settings.TAGS.items()]
ROLE_POLICY = "invoke-gateway"
LOG_GROUP_PREFIXES = (f"/aws/lambda/{settings.PROJECT}-", f"/aws/bedrock-agentcore/runtimes/{settings.PROJECT}_")
BOOTSTRAP_STACK = "CDKToolkit"


@dataclass(frozen=True)
class Step:
    description: str
    apply: Callable[[], None] | None = None  # None: nothing to change.


def setup_steps(client: Clients, account: str, sap_key: dict[str, str], seed_dir: Path) -> list[Step]:
    store = DynamoStore(settings.TABLE, client("dynamodb"))
    files = sum(1 for path in seed_dir.rglob("*") if path.is_file())
    return [
        _table_step(client("dynamodb")),
        _role_step(client("iam"), account, settings.ACTION_ROLE, "the Action agent's gateway calls"),
        _role_step(client("iam"), account, settings.AGENTS_ROLE,
                   "the Evidence and Impact agents' gateway calls outside the runtime"),
        _parameter_step(client("ssm"), sap_key),
        Step(f"Load the {files} files of data/seed/ into {settings.TABLE}", lambda: reset_table(seed_dir, store)),
    ]


def cleanup_steps(client: Clients, include_bootstrap: bool = False) -> list[Step]:
    cloudformation, dynamodb, iam, ssm = (client(name) for name in ("cloudformation", "dynamodb", "iam", "ssm"))
    steps = [_delete_stack(cloudformation, name) for name in _project_stacks(cloudformation)]
    if _exists(lambda: dynamodb.describe_table(TableName=settings.TABLE), "ResourceNotFoundException"):
        steps.append(Step(f"Delete DynamoDB table {settings.TABLE}", lambda: _delete_table(dynamodb)))
    for role in (settings.ACTION_ROLE, settings.AGENTS_ROLE):
        if _exists(lambda role=role: iam.get_role(RoleName=role), "NoSuchEntity"):
            steps.append(Step(f"Delete IAM role {role}", lambda role=role: _delete_role(iam, role)))
    if _exists(lambda: ssm.get_parameter(Name=settings.SAP_PARAMETER), "ParameterNotFound"):
        steps.append(Step(f"Delete SSM parameter {settings.SAP_PARAMETER}",
                          lambda: ssm.delete_parameter(Name=settings.SAP_PARAMETER)))
    steps += _log_group_steps(client("logs"))
    if include_bootstrap:
        steps += _bootstrap_steps(cloudformation, client("s3"), client("ecr"))
    return steps or [Step("Nothing to delete")]


def run(steps: list[Step], apply: bool) -> None:
    """Print the steps; with apply, make each change in order."""
    for step in steps:
        if step.apply is None:
            print(f"  ok    {step.description}")
        elif apply:
            print(f"  ...   {step.description}", flush=True)
            step.apply()
        else:
            print(f"  todo  {step.description}")
    if not apply and any(step.apply for step in steps):
        print("Dry run: nothing changed. Run again with --apply to make these changes.")


def deployed(project_dir: Path) -> dict[str, str]:
    """ARNs of the deployed runtime, its role, and the gateway, and the gateway's URL, from the
    AgentCore CLI's state file.

    Empty before the first deploy; a key is missing while its resource is not deployed.
    """
    path = project_dir / "agentcore" / ".cli" / "deployed-state.json"
    if not path.exists():
        return {}
    found = {}
    for target in json.loads(path.read_text(encoding="utf-8")).get("targets", {}).values():
        resources = target.get("resources") or {}
        runtime = resources.get("runtimes", {}).get(settings.RUNTIME)
        if runtime:
            found.update(runtime_arn=runtime["runtimeArn"], runtime_role_arn=runtime["roleArn"])
        gateways = (resources.get("mcp") or {}).get("gateways") or resources.get("gateways") or {}
        gateway = gateways.get(settings.GATEWAY)
        if gateway:
            found["gateway_arn"] = gateway["gatewayArn"]
            if gateway.get("gatewayUrl"):
                found["gateway_url"] = gateway["gatewayUrl"]
    return found


def _table_step(dynamodb) -> Step:
    if _exists(lambda: dynamodb.describe_table(TableName=settings.TABLE), "ResourceNotFoundException"):
        return Step(f"DynamoDB table {settings.TABLE} exists")

    def create() -> None:
        dynamodb.create_table(
            TableName=settings.TABLE,
            AttributeDefinitions=[{"AttributeName": KEY, "AttributeType": "S"}],
            KeySchema=[{"AttributeName": KEY, "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
            Tags=TAG_LIST,
        )
        dynamodb.get_waiter("table_exists").wait(TableName=settings.TABLE)

    return Step(f"Create DynamoDB table {settings.TABLE} (on-demand billing)", create)


def _role_step(iam, account: str, name: str, calls: str) -> Step:
    # Trusting the account delegates to IAM policies: only identities granted sts:AssumeRole on the role can use
    # it, such as the runtime's role or a developer running the agents locally.
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"AWS": f"arn:aws:iam::{account}:root"}, "Action": "sts:AssumeRole"}]}
    policy = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Action": "bedrock-agentcore:InvokeGateway",
        "Resource": f"arn:aws:bedrock-agentcore:{settings.REGION}:{account}:gateway/*"}]}
    exists = _exists(lambda: iam.get_role(RoleName=name), "NoSuchEntity")

    def apply() -> None:
        if not exists:
            iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust),
                            Description=f"CLEAR: signs {calls}", Tags=TAG_LIST)
        iam.put_role_policy(RoleName=name, PolicyName=ROLE_POLICY, PolicyDocument=json.dumps(policy))

    verb = "Refresh the gateway permission of" if exists else "Create"
    return Step(f"{verb} IAM role {name} for {calls}", apply)


def _parameter_step(ssm, sap_key: dict[str, str]) -> Step:
    missing = [name for name in settings.SAP_SETTINGS if not sap_key.get(name)]
    if missing:
        return Step(f"Skip SSM parameter {settings.SAP_PARAMETER}: .env lacks {', '.join(missing)}, "
                    "so predictions will use the baseline")
    value = json.dumps({name: sap_key[name] for name in settings.SAP_SETTINGS})
    exists = _exists(lambda: ssm.get_parameter(Name=settings.SAP_PARAMETER), "ParameterNotFound")

    def apply() -> None:
        if exists:  # Overwriting keeps the tags; SSM refuses tags together with Overwrite.
            ssm.put_parameter(Name=settings.SAP_PARAMETER, Value=value, Type="SecureString", Overwrite=True)
        else:
            ssm.put_parameter(Name=settings.SAP_PARAMETER, Value=value, Type="SecureString",
                              Description="SAP AI Core service key for the CLEAR prediction tool", Tags=TAG_LIST)

    verb = "Update" if exists else "Create"
    return Step(f"{verb} SSM SecureString parameter {settings.SAP_PARAMETER} from the SAP AI Core key in .env", apply)


def _project_stacks(cloudformation) -> list[str]:
    names = []
    for page in cloudformation.get_paginator("describe_stacks").paginate():
        names += [stack["StackName"] for stack in page["Stacks"]
                  if stack["StackName"].startswith(settings.STACK_PREFIX)]
    return names


def _delete_stack(cloudformation, name: str, what: str = "runtime, gateway, Lambda function, and their roles") -> Step:
    def apply() -> None:
        cloudformation.delete_stack(StackName=name)
        cloudformation.get_waiter("stack_delete_complete").wait(
            StackName=name, WaiterConfig={"Delay": 15, "MaxAttempts": 120})

    return Step(f"Delete CloudFormation stack {name} ({what})", apply)


def _delete_table(dynamodb) -> None:
    dynamodb.delete_table(TableName=settings.TABLE)
    dynamodb.get_waiter("table_not_exists").wait(TableName=settings.TABLE)


def _delete_role(iam, role: str) -> None:
    for name in iam.list_role_policies(RoleName=role)["PolicyNames"]:
        iam.delete_role_policy(RoleName=role, PolicyName=name)
    for policy in iam.list_attached_role_policies(RoleName=role)["AttachedPolicies"]:
        iam.detach_role_policy(RoleName=role, PolicyArn=policy["PolicyArn"])
    iam.delete_role(RoleName=role)


def _log_group_steps(logs) -> list[Step]:
    steps = []
    for prefix in LOG_GROUP_PREFIXES:
        for page in logs.get_paginator("describe_log_groups").paginate(logGroupNamePrefix=prefix):
            for group in page["logGroups"]:
                name = group["logGroupName"]
                steps.append(Step(f"Delete log group {name}",
                                  lambda name=name: logs.delete_log_group(logGroupName=name)))
    return steps


def _bootstrap_steps(cloudformation, s3, ecr) -> list[Step]:
    """The CDK bootstrap stack keeps its bucket and image repository when deleted; remove those too."""
    try:
        [stack] = cloudformation.describe_stacks(StackName=BOOTSTRAP_STACK)["Stacks"]
    except ClientError as error:
        if error.response["Error"]["Code"] == "ValidationError":  # CloudFormation's answer for a missing stack.
            return []
        raise
    outputs = {output["OutputKey"]: output["OutputValue"] for output in stack.get("Outputs", [])}
    steps = [_delete_stack(cloudformation, BOOTSTRAP_STACK, "CDK bootstrap for this account and region")]
    if outputs.get("BucketName"):
        bucket = outputs["BucketName"]
        steps.append(Step(f"Empty and delete S3 bucket {bucket}", lambda: _delete_bucket(s3, bucket)))
    if outputs.get("ImageRepositoryName"):
        repository = outputs["ImageRepositoryName"]
        steps.append(Step(f"Delete ECR repository {repository}",
                          lambda: ecr.delete_repository(repositoryName=repository, force=True)))
    return steps


def _delete_bucket(s3, bucket: str) -> None:
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket):
        objects = [{"Key": version["Key"], "VersionId": version["VersionId"]}
                   for version in page.get("Versions", []) + page.get("DeleteMarkers", [])]
        if objects:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
    s3.delete_bucket(Bucket=bucket)


def _exists(call: Callable[[], object], missing: str) -> bool:
    try:
        call()
    except ClientError as error:
        if error.response["Error"]["Code"] == missing:
            return False
        raise
    return True
