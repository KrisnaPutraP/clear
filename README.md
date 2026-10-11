# CLEAR — Cross-Border Supply Chain Exception Resolution Agent

Agentic AI Hackathon 2026 · Track A: Intelligent Supply Chain · Team Cookusan

> ERP runs the process. Humans chase the exceptions. CLEAR resolves them.

CLEAR turns a cross-border shipment exception into an evidence-backed,
validated recovery plan. A human approves every write action. How it works:
[docs/architecture.md](docs/architecture.md).

**Status:** work in progress. Locked decisions: `docs/PLAN.md`.

## Run locally

Requires Python 3.12.

```
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env          # macOS/Linux: cp; then fill in what you have
python scripts/reset_data.py
pytest
streamlit run app/streamlit_app.py
```

The agents run on Claude Sonnet 4.6 in SAP AI Core (`CLEAR_LLM_BACKEND=aicore`
with the team's AI Core service key and `SAP_LLM_DEPLOYMENT_ID`) or on Amazon
Bedrock (`CLEAR_LLM_BACKEND=bedrock` with `CLEAR_BEDROCK_MODEL_ID` and AWS
credentials). Both use the Bedrock Converse API, so the agent code is the same.
Without either, `CLEAR_UI_SCRIPTED=1` lets you click through the UI with a
scripted model, for development only. Resolution time comes from
SAP-RPT-1.6 when the SAP AI Core settings are filled in, with an automatic
fallback to a baseline median.

## Run on AWS

The same code deploys to Amazon Bedrock AgentCore: the agents on AgentCore
Runtime, the tools in a Lambda function behind AgentCore Gateway, the data in
DynamoDB. Steps, resources, and cleanup: `docs/deployment.md`.