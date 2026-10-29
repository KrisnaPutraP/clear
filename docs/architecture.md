# CLEAR architecture

CLEAR turns a cross-border shipment exception into a validated recovery
plan. Its design rule: **the LLM proposes, code computes and validates, a
human approves.**

SAP provides the AI and the planner's assistant: the agents reason with
Claude Sonnet 4.6 and predict resolution times with SAP-RPT-1.6, both in SAP
AI Core, and a planner can work a case from SAP Joule. AWS provides the
agent infrastructure and its governance: the agents are built with Strands,
and every tool call passes AgentCore Gateway, where Cedar policies decide
which agent may call which tool, before the tools run in AWS Lambda on
DynamoDB.

## Deployed system

```mermaid
flowchart LR
    subgraph machine["Presenter's machine"]
        ws["Next.js workspace<br/>(or the Streamlit UI)"]
        api["FastAPI service<br/>UI contract and Strands agents"]
    end
    subgraph sap["SAP BTP"]
        joule["SAP Joule<br/>CLEAR assistant"]
        dest["BTP destination"]
        cf["Cloud Foundry app<br/>A2A server and Strands agents"]
        llm["SAP AI Core<br/>Claude Sonnet 4.6"]
        rpt["SAP AI Core<br/>SAP-RPT-1.6"]
    end
    subgraph aws["AWS, us-west-2"]
        gw["AgentCore Gateway<br/>IAM authorization"]
        pol["AgentCore Policy<br/>Cedar: which role may<br/>call which tool"]
        fn["AWS Lambda<br/>nine deterministic tools"]
        db[("Amazon DynamoDB<br/>mock S/4HANA, documents,<br/>records, case log")]
        ssm["SSM Parameter Store<br/>SAP AI Core key"]
    end
    planner(["Planner"]) --> ws
    planner --> joule
    ws -- "events, decisions,<br/>polls the timeline" --> api
    joule -- "agent-request (A2A)" --> dest --> cf
    api -- "reason and plan" --> llm
    cf -- "reason and plan" --> llm
    api -- "tool calls over MCP,<br/>signed with each agent's role" --> gw
    cf -- "tool calls over MCP,<br/>signed with each agent's role" --> gw
    api -- "case log" --> db
    cf -- "case log" --> db
    gw -- "authorize each call" --> pol
    gw --> fn
    fn --> db
    fn -- "SAP AI Core key" --> ssm
    fn -- "predict resolution time" --> rpt
```

| Part | What it does |
|---|---|
| Logistics event feed (simulated) | Starts a case; in production the same payload would come from Amazon EventBridge |
| Next.js workspace and FastAPI service | The planner's workspace: event feed, live agent timeline, documents, inventory, approval desk; FastAPI serves the UI contract ([web-development.md](web-development.md)). The Streamlit UI offers the same workflow |
| SAP Joule | The planner can start a case, read its status and plan, and approve or reject a validated transfer in Joule; Joule calls CLEAR over A2A |
| Strands agents | The orchestrator and three specialists, with a case-log hook on every agent; they run in the FastAPI (or Streamlit) process for the workspace, and in a Cloud Foundry app on SAP BTP for Joule |
| Claude Sonnet 4.6 | The agents' LLM, in SAP AI Core's generative AI hub, called with the Bedrock Converse API; one setting (`CLEAR_LLM_BACKEND`) switches the agents to Amazon Bedrock |
| AgentCore Gateway | The only way to the tools; each agent signs its calls with its own IAM role |
| AgentCore Policy | Cedar policies on the gateway: the reading agents' role may only read and assess; only the Action agent's role may validate and write, and the STO write needs an approval ID |
| Lambda tools | Deterministic Python: every number comes from data or from code, never from the LLM |
| DynamoDB | Mock S/4HANA with the entity and field names of SAP's published APIs, plus documents, records, and the case log; shared by every front door, so a case started in one shows in the others |
| SAP-RPT-1.6 | Predicts how long the exception will take, from past exceptions; falls back to a baseline median and says so |

## Where it runs

The same code runs in four configurations:

| Configuration | Agents | Tools and data | Used for |
|---|---|---|---|
| Local | Presenter's machine | In the same process, on JSON files in `data/runtime/` | Development, tests, and the demo's fallback when the network fails |
| Gateway (deployed) | Presenter's machine, in the FastAPI or Streamlit process | AgentCore Gateway, Lambda, DynamoDB, Cedar policies | The demo in the workspace |
| Joule (deployed) | Cloud Foundry app on SAP BTP | AgentCore Gateway, Lambda, DynamoDB, Cedar policies | The demo in Joule |
| Runtime | AgentCore Runtime | AgentCore Gateway, Lambda, DynamoDB, Cedar policies | Built and tested with stand-ins; not deployed, because the team's AWS account has no AgentCore Runtime quota |

Deployment details: [deployment.md](deployment.md).

## SAP Joule as a front door

```mermaid
sequenceDiagram
    actor P as Planner
    participant J as SAP Joule
    participant C as CLEAR A2A server<br/>(Cloud Foundry)
    participant A as Agents, gateway,<br/>Cedar, tools
    P->>J: status of SHP-1001
    J->>C: agent-request (A2A message/send)
    C->>A: read the case and its records
    C-->>J: plan, numbers with their sources,<br/>"awaiting approval: VAL-0002"
    P->>J: approve VAL-0002
    J->>C: agent-request
    C->>A: record the approval, run the Action agent
    A-->>C: STO created through the gateway
    C-->>J: STO created, case monitoring
```

- Joule chooses CLEAR's skill and forwards the planner's message. CLEAR does
  not use an LLM to read the message: it matches IDs and keywords
  (`clear_app.joule`), and an approval must name the validation it approves.
- Joule waits at most 60 seconds for an answer, and a case takes 24 to 136
  seconds. CLEAR answers within 40 seconds: a run continues in the
  background, the answer shows its latest steps, and the planner asks for
  the status again.
- Every number in the answer is read from the case records, as in the
  workspace. The approval is recorded as "Planner via Joule": the
  destination's credentials identify Joule, not the person; a production
  setup would pass the user's identity through.

## A case, step by step

S1 with the planner's approval, in the deployed configuration:

```mermaid
sequenceDiagram
    actor P as Planner
    participant O as Orchestrator
    participant S as Specialist agents
    participant G as AgentCore Gateway<br/>and Cedar policies
    participant T as Lambda tools
    P->>O: Event: customs document hold
    O->>S: Evidence: reconcile documents, read stock
    S->>G: read tools, signed with the agents role
    G->>T: allowed
    T-->>S: packing list disagrees with PO and invoice
    O->>S: Impact: predict, assess the current plan
    S->>G: predict_resolution_time, calculate_supply_risk
    G->>T: allowed
    T-->>S: 3.1 days (SAP-RPT-1.6), shortage 34 t
    O->>S: Action: validate moving the whole shortage
    S->>G: validate_action, signed with the Action role
    G->>T: allowed
    T-->>S: rejected: plant 1200 would fall below safety stock, at most 20 t
    O->>S: Impact: assess 20 t with fewer orders served
    T-->>S: 20 t with critical and high orders is covered
    O->>S: Action: validate 20 t
    T-->>S: valid (VAL-0002)
    O-->>P: Plan awaiting approval
    P->>O: Approve (APR-0001), in the workspace or in Joule
    O->>S: Action: create the STO
    S->>G: create_stock_transport_order(VAL-0002, APR-0001)
    G->>T: allowed: Action role with an approval ID
    T-->>S: STO created, stock verified
    O-->>P: Monitoring
```

The numbers are from a live run; the timeline in the workspace shows the
same steps as they happen.

## Agents and tools

```mermaid
flowchart TB
    o["Orchestrator<br/>case manager: picks the next step,<br/>re-plans on new events"]
    e["Evidence agent<br/>read only"]
    i["Impact & Options agent"]
    a["Action agent<br/>the only write path"]
    o --> e
    o --> i
    o --> a
    e --- te["get_shipment, get_purchase_order,<br/>get_documents, get_inventory,<br/>reconcile_documents"]
    i --- ti["predict_resolution_time (SAP-RPT-1.6),<br/>calculate_supply_risk"]
    a --- ta["validate_action,<br/>create_stock_transport_order,<br/>get_inventory"]
    e -. "signs with the agents role" .- gwa(["AgentCore Gateway"])
    i -. "signs with the agents role" .- gwa
    a -. "signs with the Action role" .- gwa
```

The orchestrator chooses the path per exception. A document hold starts
with reconciling the documents; port congestion starts from the impact
assessment. When the validator rejects a transfer, or a new event arrives,
the orchestrator re-plans.

## Where the numbers come from

| Number | Source |
|---|---|
| Stock, safety stock, orders | Mock S/4HANA, read by the tools |
| Document fields | Extracted by the LLM with quotes; `reconcile_documents` checks each quote against the document and compares the values |
| Resolution time | SAP-RPT-1.6, or the baseline median when it is unavailable; every prediction names its source |
| Coverage, shortage, deferred orders, cost | `calculate_supply_risk`, deterministic |
| Feasible transfer | `validate_action`, deterministic; a transfer counts as infeasible only on a validation that says so |
| STO quantity | Taken from the validation record, so it equals what was validated and approved |

Agents pass only IDs and decision variables to the tools. A recovery plan
cites record IDs (prediction, assessments, validation), and the workspace
and Joule fill in every number from those records: the LLM cannot mistype a
quantity into the system. The plan check rejects a plan that cites a record
that does not exist, or that defers orders without a transfer and without
telling a human.

## Governance: five layers before an STO exists

1. **Tool contract.** The write tool takes a `validation_id` and an `approval_id`, nothing else.
2. **Validator.** Four business rules: the source plant stays above safety stock, the transfer arrives in time, no over-transfer, the right material and plants.
3. **Human approval.** A planner approves or rejects in the workspace, which shows the plan, the validation, and the source of every number, or in Joule, where the approval must name the validation.
4. **Gateway policy.** Cedar in AgentCore Policy, outside the agents: each agent's IAM role may call only its own tools, the STO write is forbidden unless the Action agent's role calls it with an approval ID, and an administrator without these roles reaches no tool at all. This holds for the agents on the presenter's machine and on SAP BTP alike.
5. **Code check.** The tool verifies that the approval exists, is for that validation, is an approval and not a rejection, and has not been used before.

Every step lands in the case log, which serves as the timeline, the audit
trail, and the case state that lets a run pause for approval and resume.
