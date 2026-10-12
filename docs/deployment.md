# Deploying CLEAR on AWS

CLEAR runs the same code locally and on AWS. Locally, the agents call the
tools in-process and the data lives in JSON files. On AWS, every tool call
goes through AgentCore Gateway to an AWS Lambda function, the data lives in
DynamoDB, and Cedar policies on the gateway decide which agent may call which
tool. The tool logic (`src/clear_tools/`) is the same package in both cases.

The agents themselves can run in two places:

- **On the presenter's laptop (deployed now).** The team's account has no
  AgentCore Runtime quota, so the agents run on the laptop with their tools
  behind the gateway: `clear_aws.remote.GatewayAgents`, which runs the
  runtime's own code in-process.
- **On AgentCore Runtime (built, not deployed).** The same code as a runtime
  in AWS, for an account with Runtime quota: `clear_aws.runtime` and
  `deploy/runtime/`.

Setting up a machine to use the deployment, without deploying anything:
[setup.md](setup.md).

## What runs where

| Part | Where | Created by |
|---|---|---|
| Orchestrator and the three specialist agents, one process | The presenter's laptop (on AgentCore Runtime `cookusanhackathon_clear` in the Runtime variant) | — (AgentCore CLI) |
| The nine tools | Lambda function `cookusanhackathon-clear-tools` behind AgentCore Gateway `cookusanhackathon-tools` (AWS IAM authorization) | AgentCore CLI |
| Which agent may call which tool | Cedar policies in the AgentCore policy engine `clear_policies`, on the gateway | AgentCore CLI |
| Mock S/4HANA, documents, records, case log | DynamoDB table `cookusan-hackathon-clear-data` | `scripts/aws_setup.py` |
| The Evidence and Impact agents' identity at the gateway | IAM role `cookusan-hackathon-agents` (the runtime's own role in the Runtime variant) | `scripts/aws_setup.py` |
| The Action agent's identity at the gateway | IAM role `cookusan-hackathon-action-agent` | `scripts/aws_setup.py` |
| SAP AI Core service key for SAP-RPT-1.6 | SSM SecureString parameter `/cookusan-hackathon/sap-aicore` | `scripts/aws_setup.py` |
| The agents' model | Claude Sonnet 4.6 in SAP AI Core, outside AWS | The hackathon organizers |
| Demo UI | Streamlit on the presenter's laptop | — |

A run, step by step:

1. The UI records the logistics event (or the planner's decision) in DynamoDB
   and starts the agents for that case (`src/clear_aws/remote.py`).
2. The agents are built as in a local run (`src/clear_aws/runtime.py`). Their
   Strands tools are the ones used locally, with the same names,
   descriptions, and input schemas; only the call travels, over MCP signed
   with SigV4, to the gateway (`src/clear_aws/gateway.py`).
3. The gateway checks the call against the Cedar policies, then invokes the
   Lambda function, which runs the tool against DynamoDB and returns its
   result or the reason it refused (`src/clear_aws/lambda_tools.py`).
4. The agents' hooks write the case log to DynamoDB, which the UI polls for
   the live timeline.

Each agent signs its gateway calls with its own IAM role: the Action agent,
the only one holding the write tool, with `cookusan-hackathon-action-agent`,
and the Evidence and Impact agents with `cookusan-hackathon-agents`. The
laptop's identity assumes both and needs no access to the tools itself. The
Cedar policies tell the agents apart by these roles.

Every resource carries the tags `Project=ID-Hackathon-2026`, `Team=Cookusan`,
and `DeleteAfter=2026-10-31`. Resources created by CLEAR's scripts use the
prefix `cookusan-hackathon`. The AgentCore CLI allows only letters and digits
in a project name and derives the other names from it, so its resources
start with `cookusanhackathon`.

## Prerequisites

- An IAM identity with administrator access in the account, signed in with
  `aws login --profile <name>` (AWS CLI 2.32 or later), and that profile in
  `AWS_PROFILE` in `.env`.
- `pip install -e ".[dev,aws]"`: the gateway client and the `botocore` CRT
  that lets the Python scripts use `aws login` credentials.
- Node.js 20 or later and the AgentCore CLI: `npm install -g @aws/agentcore`
  (written against version 0.31.1).
- `uv` on the PATH (`pip install uv`): the CLI packages the code bundles with
  it.
- The SAP AI Core settings in `.env` ([setup.md](setup.md)), which
  `aws_setup.py` stores for the Lambda function. Without them, predictions
  use the baseline and say so.

The Runtime variant also needs AgentCore Runtime quota and, because the
deployed runtime runs its agents on Amazon Bedrock, Bedrock model quota and
`CLEAR_BEDROCK_MODEL_ID` in `.env`. A new account can start with both quotas
at 0 (ours did, on the AWS Free plan): model calls then fail with "Operation
not allowed", and the deploy stops at the runtime with "maxAgents limit
exceeded" and rolls back. Only AWS Support restores them: Service Quotas
accepts only values above the AWS default, and access to Anthropic models is
a separate account-level check. To check the runtime quota (the AWS default
is 1000):

```
aws service-quotas list-service-quotas --service-code bedrock-agentcore --query "Quotas[?QuotaName=='Total Agents per Account'].Value"
```

Running the runtime's agents on Claude in SAP AI Core instead would also need
the AI Core key in the runtime, which is not wired up yet.

## Deploy

Once, create the AgentCore CLI project and the resources the CLI does not
manage:

```
cd deploy
agentcore create --project-name cookusanhackathon --no-agent
cd ..
python scripts/aws_setup.py             # dry run: what exists, what would be created
python scripts/aws_setup.py --apply     # table, both IAM roles, SSM parameter, seed data
```

Then build and deploy the gateway and the Lambda function, without the
runtime:

```
python scripts/build_deploy.py --no-runtime
cd deploy/cookusanhackathon
agentcore validate
agentcore deploy                        # the first deploy also bootstraps CDK
cd ../..
python scripts/aws_setup.py             # prints the gateway lines for .env
```

For the Runtime variant, run `build_deploy.py` without `--no-runtime`;
`aws_setup.py` then prints the `CLEAR_AGENT_RUNTIME_ARN` line for `.env`
instead.

`scripts/build_deploy.py` writes into `deploy/cookusanhackathon/`, which is
not in Git:

- `agentcore/agentcore.json`, generated by `src/clear_aws/agentcore.py`. The
  gateway's tool definitions come from the agents' Strands tools.
- `app/clear/`: the runtime bundle, from `deploy/runtime/` plus the
  `clear_tools`, `clear_agents`, and `clear_aws` packages. Its dependencies,
  in `deploy/runtime/pyproject.toml`, are pinned; `strands-agents` matches
  the version the tests run.
- `app/clear-tools/`: the Lambda bundle, from `deploy/tools/` plus
  `clear_tools` and four `clear_aws` modules. It needs nothing beyond the
  standard library and the boto3 that the Lambda runtime provides.

Code changes only reach AWS through `build_deploy.py` followed by
`agentcore deploy`.

`agentcore deploy` bootstraps CDK without the project tags. To tag the
bootstrap stack too, bootstrap it yourself before the first deploy, from
`deploy/cookusanhackathon/agentcore/cdk`:

```
npx cdk bootstrap aws://<account>/us-west-2 --tags Project=ID-Hackathon-2026 --tags Team=Cookusan --tags DeleteAfter=2026-10-31
```

If the first deploy fails, CloudFormation rolls the stack back but keeps the
Lambda function's log group, and the next deploy stops because that group
already exists. Delete it before deploying again:

```
aws logs delete-log-group --log-group-name /aws/lambda/cookusanhackathon-clear-tools
```

## Check and run

```
python scripts/check_policies.py                        # what the policies allow and deny
python scripts/run_scenario.py S2 --gateway             # the short scenario through the gateway
python scripts/run_scenario.py S1 --approve --eta-slip --gateway   # the hero scenario end to end
streamlit run app/streamlit_app.py
```

`--gateway` runs reset the table first and print the case log, where a
failure shows; the gateway is set to return error details. With
`AGENTCORE_GATEWAY_TOOLS_URL` in `.env` and no `CLEAR_AGENT_RUNTIME_ARN`, the
UI runs in this mode, and its sidebar says "tools via AgentCore Gateway". In
the Runtime variant, use `--cloud` instead of `--gateway`; the sidebar then
says "AgentCore Runtime".

Before each demo run, reset the data with the UI's button or with
`python scripts/reset_data.py --aws`.

To test the Lambda function alone, invoke it with the client context the
gateway would send (PowerShell):

```
$context = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('{"custom":{"bedrockAgentCoreToolName":"clear-tools___get_shipment"}}'))
aws lambda invoke --function-name cookusanhackathon-clear-tools --client-context $context --cli-binary-format raw-in-base64-out --payload '{\"shipment_id\":\"SHP-1001\"}' out.json
```

## Cedar policies on the gateway

Company rules are enforced outside the agents, at the gateway
(`src/clear_aws/policy.py`). The gateway denies every tool call that no
policy permits, and a `forbid` always wins over a `permit`:

| Policy | Rule |
|---|---|
| `agents_read_and_assess` | The Evidence and Impact agents' role (`cookusan-hackathon-agents`, or the runtime's own role in the Runtime variant) may call the read and assessment tools |
| `action_agent_tools` | The Action agent's role may call `validate_action`, `create_stock_transport_order`, and `get_inventory` |
| `sto_needs_action_agent_and_approval` | `create_stock_transport_order` is forbidden for IAM callers unless the caller is the Action agent's role and the call carries an approval ID (`APR-…`) |

Each role gets exactly the tools its agents hold in code
(`tests/test_policy.py`), and the code still checks the approval record
itself (`src/clear_tools/sto.py`). Even an administrator calling the gateway
directly cannot create a stock transport order.

A policy that names specific tools has to name the gateway's ARN, so attach
the policies after a first deploy without them, first in `LOG_ONLY` mode:

```
python scripts/build_deploy.py --no-runtime --policy log-only   # reads the gateway's ARN from the CLI's state
cd deploy/cookusanhackathon && agentcore validate && agentcore deploy
cd ../.. && python scripts/run_scenario.py S1 --approve --gateway
```

In `LOG_ONLY` mode the gateway evaluates every call without applying the
decision. Then build with `--policy enforce`, deploy again, and repeat the S1
run. In the Runtime variant, leave out `--no-runtime`: the policies then name
the runtime's role.

After every change to the policies, run `python scripts/check_policies.py`.
It calls the gateway as each role and as an administrator without one, and
fails when an outcome breaks a rule. AgentCore does not check the STO forbid
at deploy time (see below), so this is the check that does. None of its calls
can write.

## Checked on the deployment

Deployed on 12 October 2026 without the runtime (gateway, Lambda function,
DynamoDB table, Cedar policies in ENFORCE mode), with the agents on a laptop:

- S1 (both events) and S2 ran end to end through the gateway, approval and
  STO included, with the policies enforced; no call they needed was denied.
- The gateway hands the Lambda function's JSON result to the agent as the
  tool result's text, and a tool's error comes back as the exception the
  tool raised (for example `LookupError: Unknown validation_id`).
- `ssm:GetParameter` is enough for the Lambda function to read the
  SecureString, and the 60-second timeout covers a cold start plus
  SAP-RPT-1.6: S1's predictions came from SAP-RPT-1.6 through the function.
- The project tags reach the gateway, the Lambda function and its log group,
  the table, the parameter, and both roles.
- What the policies allow and deny, called directly (`check_policies.py`):

  | Caller | Tool | Result |
  |---|---|---|
  | Agents role | `get_shipment` | Allowed |
  | Agents role | `validate_action` | Denied by default |
  | Action role | `create_stock_transport_order`, approval `X-1` | Denied by `sto_needs_action_agent_and_approval` |
  | Action role | `create_stock_transport_order`, approval `APR-9999` | Allowed; the tool refuses the unknown validation |
  | Action role | `predict_resolution_time` | Denied by default |
  | Administrator, no role | `get_shipment` | Denied by default |

- AgentCore checks each new policy against the policies that already exist,
  and CloudFormation creates the three in no fixed order. Checked before the
  Action agent's permit existed, the forbid denies every STO request, and the
  deploy failed as "Overly Restrictive". The forbid is therefore scoped to
  IAM principals and sets `validationMode: IGNORE_ALL_FINDINGS`
  (`src/clear_aws/policy.py`); the table above shows it still allows the
  approved STO.

Not checked: the runtime itself, which needs the AgentCore Runtime quota.

## Clean up

```
python scripts/aws_cleanup.py                         # dry run: what would be deleted
python scripts/aws_cleanup.py --apply                 # stack, table, both roles, parameter, log groups
python scripts/aws_cleanup.py --apply --include-bootstrap   # also the CDK bootstrap stack, bucket, repository
```

`--include-bootstrap` removes what `agentcore deploy` set up for CDK in this
account and region; skip it if anything else in the account uses CDK. Then
delete `deploy/cookusanhackathon/`.

## Tests without AWS

`tests/aws_fakes.py` stands in for DynamoDB, the gateway, the Lambda
function, and AgentCore Runtime, and checks every request against the AWS
API models that botocore ships. The tests run S1 and S2 through the whole
deployed path, both with the agents on AgentCore Runtime and on the laptop,
check the generated `agentcore.json` against the CLI's rules (it also passes
`agentcore validate`), check that the Lambda bundle imports nothing the
Lambda runtime lacks, and check every request the setup and cleanup scripts
make, with botocore's Stubber.
