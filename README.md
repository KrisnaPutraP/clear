# CLEAR — Cross-Border Supply Chain Exception Resolution Agent

Agentic AI Hackathon 2026 · Track A: Intelligent Supply Chain · Team Cookusan

> ERP runs the process. Humans chase the exceptions. CLEAR resolves them.

When an imported shipment is held at the port, a planner today pieces the
case together by hand from the ERP, the shipping documents, stock reports,
and approvals before anything moves. CLEAR turns such an exception
into an evidence-backed, validated recovery plan, and a human approves every
write before it reaches the ERP.

## How it works

- A logistics event (simulated) starts a case.
- An orchestrator and three specialist agents, built with Strands, work it:
  the **Evidence** agent reconciles the shipping documents, the **Impact &
  Options** agent predicts how long the exception lasts and scores recovery
  options, and the **Action** agent validates and, once approved, creates the
  stock transport order (STO).
- The agents reason with **Claude Sonnet 4.6 in SAP AI Core**; resolution
  times come from **SAP-RPT-1.6**, also in SAP AI Core.
- Every tool call goes through **AgentCore Gateway**, where **Cedar
  policies** let each agent's IAM role call only its own tools and forbid the
  STO without the Action agent and an approval. The tools run in **AWS
  Lambda** on **DynamoDB**.
- The planner follows the case in a **Next.js workspace** and approves there,
  or works it from **SAP Joule**: Joule calls CLEAR over A2A through a BTP
  destination, and the agents answer from a Cloud Foundry app on SAP BTP,
  with the same tools, gateway, and policies.
- **The LLM proposes, code computes and validates, a human approves:** every
  number comes from data, deterministic tools, or SAP-RPT-1.6, and shows its
  source.

Diagrams and details: [docs/architecture.md](docs/architecture.md).

## Status

Working end to end (29 October 2026): both demo scenarios run live with the
agents on Claude in SAP AI Core and the tools on AWS behind AgentCore Gateway
with the Cedar policies enforced. A planner works a case in the Next.js
workspace (or the Streamlit UI), whose agents run on the presenter's
machine, or in SAP Joule, whose agents run on SAP BTP Cloud Foundry; both
share the same data. AgentCore Runtime is built but not deployed, since the
team's AWS account has no Runtime quota. Twenty evaluation variants check
the agents' decisions against an oracle; the final run on 28 October passes
every check ([docs/evaluation.md](docs/evaluation.md)). Prototype boundaries
are described below.

The current online demo uses **SAP Joule with the A2A backend on Cloud
Foundry**. The Next.js frontend and FastAPI service are available locally;
they are not deployed as a public website.

## Try the Joule demo

Use the team's CLEAR assistant in SAP Joule with an authorized account.
Access is provided by the team; this repository does not grant access to
the deployed assistant.

| Message | What to expect |
|---|---|
| `show open cases` | Recorded cases, with human decisions and approvals first |
| `status of SHP-1001` | The case summary, or shipment facts if no case exists yet |
| `work S1-DOC-HOLD` | Submit the prepared customs-hold event and start live analysis |
| `details of SHP-1001` | Evidence, recommendation rationale, and assessed options |
| `approve VAL-xxxx` | Approve the currently pending transfer using the ID in the reply |
| `work S1-ETA-SLIP` | Reassess the same case after the prepared ETA change |

If analysis is still running, ask for status again after about a minute.
Case and validation IDs depend on the run. `work` starts investigation; it
does not close the case. Monitoring cases remain listed. Coordinate with
the presenter before submitting events or approvals because the demo data
is shared. See the [Joule guide](docs/joule-responses.md) for commands,
rejection, and response details.

## Evidence and prototype boundaries

The recorded evaluation on 28 October covers 20 synthetic variants: all
decision and governance checks passed, with a median recovery-plan time of
79 seconds. These are bounded prototype results, not production guarantees.
The 93-minute manual comparison is an estimate, not a measured baseline.
See [evaluation](docs/evaluation.md) for the method and limitations.

- Shipments, documents, and ERP records are synthetic; approved STOs update
  the mock ERP, not a live S/4HANA system. In transit does not mean received.
- Demo events are submitted manually. A live ERP/logistics event feed is
  not connected, and emergency procurement remains a human decision.
- Agents use live model reasoning; chat commands are routed by keywords
  and IDs. Scripted mode is a separate development fallback.
- Joule approvals use a shared planner label. Per-user approval identity,
  durable job recovery, and coordination across independent writer
  processes remain production work. Run one case-writing service at a
  time against shared data.

## Quick start

Requires Python 3.12. No credentials needed for this part:

```
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env          # macOS/Linux: cp
python scripts/reset_data.py
pytest
```

To run the agents live (SAP AI Core) and the tools on AWS, follow
[docs/setup.md](docs/setup.md).

For the **Next.js + FastAPI workspace**, install `.[api,dev]`, start
`python -m uvicorn clear_app.api:create_app --factory --host 127.0.0.1 --port 8000`
from an activated environment, then run `npm ci` and `npm run dev` in
`frontend/`. Set `CLEAR_UI_SCRIPTED=1` in the API process for a development
demo without credentials. Full instructions: [docs/web-development.md](docs/web-development.md).

## Developer commands

| Command | What it does |
|---|---|
| `pytest` | All tests; the live ones run only with `CLEAR_LIVE_TESTS=1` |
| `streamlit run app/streamlit_app.py` | The demo UI; `CLEAR_UI_SCRIPTED=1` in `.env` for a scripted model |
| `python -m uvicorn clear_app.api:create_app --factory --host 127.0.0.1 --port 8000` | FastAPI adapter, one worker per store; API docs at `/docs` |
| `npm run dev` (in `frontend/`) | Next.js landing page at `http://127.0.0.1:3000`, workspace at `/workspace` |
| `python scripts/run_scenario.py S2` | The short scenario, live, printing the case timeline |
| `python scripts/run_scenario.py S1 --approve --eta-slip` | The hero scenario: exception, approval, ETA slip |
| `... --gateway` | The same with the tools on AWS behind AgentCore Gateway |
| `python scripts/run_eval.py` | The 20-variant evaluation (`--variants A1,C2` for a subset) |
| `python scripts/reset_data.py` | Fresh demo data (`--aws` for the DynamoDB table) |
| `python scripts/check_policies.py` | What the gateway's Cedar policies allow and deny |
| `python scripts/gateway_env.py` | The `.env` lines for the deployed gateway |
| `python scripts/run_joule_agent.py` | CLEAR as an A2A agent for SAP Joule (`--scripted` without credentials) |
| `python scripts/cf_env.py --gateway` | The Joule app's settings on Cloud Foundry, from `.env` |

## Repository

| Path | Contents |
|---|---|
| `app/` | Streamlit demo UI |
| `frontend/` | Next.js workspace, typed API client, and browser workflow test |
| `src/clear_tools/` | The nine deterministic tools and the mock S/4HANA; standard library only |
| `src/clear_agents/` | Strands agents, prompts, the recovery plan schema and checks, the SAP AI Core model |
| `src/clear_app/` | UI contract, FastAPI adapter, A2A server for SAP Joule, backend initialization, and settings |
| `joule/` | The SAP Joule capability that calls CLEAR over A2A |
| `src/clear_aws/` | AWS: DynamoDB store, Lambda handler, gateway client, Cedar policies, deployment config, setup |
| `src/clear_eval/` | Evaluation: variants, oracle, scoring |
| `src/clear_datagen/` | Generators of the synthetic seed data |
| `data/seed/` | The committed demo data ([data/README.md](data/README.md)) |
| `deploy/` | Templates of the code bundles for AgentCore Runtime and Lambda |
| `manifest.yml` | The Cloud Foundry app for the Joule path (`cf push`) |
| `scripts/` | Command-line entry points (table above) |
| `tests/` | Unit, scenario-invariant, and deployment tests, with stand-ins for AWS |
| `docs/` | Architecture, setup, deployment, evaluation, UI contract, contributing |

## Review the solution

- [docs/architecture.md](docs/architecture.md): how CLEAR works, with diagrams
- [docs/proposal-alignment.md](docs/proposal-alignment.md): how the demo implements the proposal, adaptations and their justification, and remaining scope
- [docs/evaluation.md](docs/evaluation.md): evaluation method, results, and limitations
- [docs/joule-responses.md](docs/joule-responses.md): Joule commands and case responses
- [data/README.md](data/README.md): the synthetic data and its generator rules

## Developer documentation

- [docs/setup.md](docs/setup.md): from a fresh clone to the full demo
- [docs/web-development.md](docs/web-development.md): Next.js and FastAPI setup, workflow, configuration, and checks
- [docs/deployment.md](docs/deployment.md): what runs on AWS and how to deploy it
- [docs/ui-contract.md](docs/ui-contract.md): the interface between the UI and the agents
- [docs/contributing.md](docs/contributing.md): contribution rules, validation, and development workflow

All data in this repository is synthetic, and every company and person name
in it is fictional.
