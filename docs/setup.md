# Setting up CLEAR

For the Next.js frontend and FastAPI backend, follow
[web-development.md](web-development.md). This page covers the existing
Streamlit workflow and the shared live-model/AWS credentials.

From a fresh clone to the full demo. Each level adds one kind of access, and
each one works without the next:

| Level | You can | You need |
|---|---|---|
| 1. Local, scripted | Run the tests; click through the UI with a scripted model | Python 3.12 |
| 2. Live agents | Run S1, S2, and the evaluation on the real model | The team's SAP AI Core service key |
| 3. Tools on AWS | Run the demo as presented: tools behind AgentCore Gateway, data in DynamoDB | An IAM user in the team's AWS account |
| 4. Deploy | Change what runs on AWS | Administrator access; see [deployment.md](deployment.md) |

The commands are for Windows (PowerShell or cmd). On macOS or Linux, use
`source .venv/bin/activate` and `cp` instead.

## 1. Local, scripted

```
git clone <repository URL>
cd clear
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
python scripts/reset_data.py
pytest
```

`pytest` should pass with two live tests skipped. `reset_data.py` copies
`data/seed/` into `data/runtime/`, the demo state the local runs change.

To click through the UI without any credentials, set `CLEAR_UI_SCRIPTED=1`
in `.env`, then:

```
streamlit run app/streamlit_app.py
```

The banner says "Scripted model". The scripted model knows only S1 and S2
with their seed numbers; it exists for UI work, not for judging the agents.

## 2. Live agents (SAP AI Core)

The agents run on Claude Sonnet 4.6, and resolution times come from
SAP-RPT-1.6, both deployed by the hackathon organizers in SAP AI Core.

1. Follow the organizers' SAP BTP instructions (the repository the team
   received after requesting SAP AI Services access). They explain how each
   participant activates a BTP account and how to fetch the team's AI Core
   service key with the team's slug.
2. Copy the service key's fields into `.env`:

   | Service key field | `.env` variable |
   |---|---|
   | `url` | `SAP_AICORE_AUTH_URL` |
   | `clientid` | `SAP_AICORE_CLIENT_ID` |
   | `clientsecret` | `SAP_AICORE_CLIENT_SECRET` |
   | `serviceurls.AI_API_URL` | `SAP_AICORE_API_URL` |

3. From the instructions' table of deployments, copy the ID of `sap-rpt-1.6`
   into `SAP_RPT_DEPLOYMENT_ID` and the ID of `anthropic--claude-4.6-sonnet`
   into `SAP_LLM_DEPLOYMENT_ID`.
4. Keep `CLEAR_LLM_BACKEND=aicore` and `CLEAR_PREDICTION_BACKEND=auto`, and
   empty `CLEAR_UI_SCRIPTED`.

Check it with the short scenario (about a minute):

```
python scripts/run_scenario.py S2
```

It ends with `CASE-0001: monitoring`: the stock covers the delay, so the
agents keep the plan. The hero scenario, with the planner's approval and the
ETA slip, ends with `needs_human_decision` after about six minutes:

```
python scripts/run_scenario.py S1 --approve --eta-slip
```

The service key is a secret: keep it only in `.env`, never in Git, a log, or
a group chat.

## 3. Tools on AWS

This is how the demo runs: the agents on your machine, every tool call
through AgentCore Gateway to a Lambda function, the data in DynamoDB, and
the Cedar policies on the gateway deciding which agent may call which tool.
The gateway and everything behind it are already deployed in the team's AWS
account (us-west-2).

**Get an IAM user.** Ask the account owner for an IAM user of your own in
the team's account, with console access. Never share the root user or
another person's IAM user. The owner attaches two policies:

- `SignInLocalDevelopmentAccess` (AWS managed), so that `aws login` works.
- This one, with the account ID in place of `<account>`. It lets you sign
  with the two agent roles, use the demo data, and find and reach the
  gateway, and nothing else:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "SignWithTheAgentRoles", "Effect": "Allow", "Action": "sts:AssumeRole",
     "Resource": ["arn:aws:iam::<account>:role/cookusan-hackathon-agents",
                  "arn:aws:iam::<account>:role/cookusan-hackathon-action-agent"]},
    {"Sid": "DemoData", "Effect": "Allow",
     "Action": ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Scan"],
     "Resource": "arn:aws:dynamodb:us-west-2:<account>:table/cookusan-hackathon-clear-data"},
    {"Sid": "FindAndReachTheGateway", "Effect": "Allow",
     "Action": ["bedrock-agentcore:ListGateways", "bedrock-agentcore:GetGateway",
                "bedrock-agentcore:InvokeGateway"],
     "Resource": "*"}
  ]
}
```

Your own identity can reach the gateway but no tool: the Cedar policies let
only the two roles through. That is what `check_policies.py` checks below.

**Sign in and connect.** Install the AWS CLI (version 2.32 or later), then:

```
pip install -e ".[dev,aws]"
aws login --profile cookusan
```

Choose IAM user sign-in, region `us-west-2`. The session lasts up to 12
hours; run `aws login --profile cookusan` again when a command says it has
expired. Put `AWS_PROFILE=cookusan` in `.env`, then let the script print the
gateway's lines for `.env`:

```
python scripts/gateway_env.py
```

**Check it:**

```
python scripts/check_policies.py
python scripts/run_scenario.py S2 --gateway
streamlit run app/streamlit_app.py
```

`check_policies.py` ends with "All 6 calls follow the policies." The UI's
sidebar now says "tools via AgentCore Gateway".

The DynamoDB table is shared by the whole team, and `--gateway` runs and the
UI's reset button start it over from the seed. Agree on who runs what before
a rehearsal.

## Running the demo

1. Reset the demo data with the button in the sidebar.
2. **S1 · Customs document hold.** The agents reconcile the documents,
   predict how long the hold lasts, propose moving the whole shortage from
   plant 1200, see the validator reject it, and settle on the largest
   feasible transfer with critical and high orders served. The approval card
   shows the plan, the validation, and where every number comes from.
3. Approve. The Action agent creates the stock transport order and checks
   both plants' stock.
4. **S1 · ETA slip.** The delay grows; no further transfer is feasible, only
   critical orders are covered, and the case goes to a human for emergency
   sourcing.
5. **S2 · Yard congestion.** The stock covers the delay; the agents keep the
   plan.

If the venue's network fails, empty `AGENTCORE_GATEWAY_TOOLS_URL` in `.env`
and restart the UI: the tools then run locally on JSON files. The agents
still need SAP AI Core, so keep a recording of the demo as the last resort.

## What is not in Git

| Item | What it is | How to get it |
|---|---|---|
| `.env` values | Keys and settings, see `.env.example` | This guide: the SAP AI Core key from the organizers' instructions, the gateway lines from `gateway_env.py` |
| `docs/PLAN.md` | The team's locked design decisions; docstrings cite its sections as `docs/PLAN.md §…` | From the team, privately |
| `docs/pitch.md` | Pitch draft: run of show, demo script, Q&A | From the team, privately |
| `docs/reference/` | Hackathon brief, organizers' slides, the proposal; confidential | From the team, privately; never commit |
| `deploy/cookusanhackathon/` | The AgentCore CLI project, generated | Only for deploying; see [deployment.md](deployment.md) |
| `data/runtime/`, `data/eval/` | Local demo state and evaluation reports, generated | `reset_data.py`, `run_eval.py` |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `UnicodeEncodeError` in the console | Windows console encoding; run `set PYTHONIOENCODING=utf-8` (cmd) or `$env:PYTHONIOENCODING="utf-8"` (PowerShell) first |
| "Your session has expired. Please reauthenticate using 'aws login'" | Run `aws login --profile cookusan` again |
| "Set CLEAR_BEDROCK_MODEL_ID…" | `CLEAR_LLM_BACKEND` is not `aicore` in `.env` |
| "SAP AI Core settings missing: …" | A variable from step 2 of level 2 is empty |
| A prediction says "SAP-RPT unavailable … [fallback]" | SAP-RPT-1.6 did not answer within `CLEAR_RPT_TIMEOUT_SECONDS`; the baseline median stood in and says so. Expected now and then; frequent when several runs share the deployment |
| "AGENTCORE_GATEWAY_TOOLS_URL is not set" | Run `gateway_env.py` and copy its lines into `.env` |
| A case ends with "Tool call not allowed due to policy enforcement" | A role or a policy changed; run `check_policies.py` |
| `check_policies.py` fails on the first call | Your IAM user lacks the policy above, or `aws login` has expired |
