# Proposal alignment and implementation decisions

CLEAR's demo preserves the proposal's core idea: investigate a cross-border
shipment exception, connect its evidence to business impact, develop a
recovery plan, validate consequential actions, obtain human approval, and
reassess the case when conditions change. The implementation narrows the
business cases and changes parts of the deployment architecture. These
adaptations do not change the problem being addressed.

This document records that relationship and the explanation for each
adaptation. It summarizes the team's three-page `CLEAR_Sokrates.pdf`
proposal in original wording; it does not reproduce the private proposal.

Assessment date: 29 October 2026. The assessment uses repository code and
documentation, including the final evaluation run of 28 October 2026 and the
SAP Joule path deployed on 29 October 2026. It is not a new live deployment
check or a new evaluation run.

The UI migration adds a Next.js workspace and a FastAPI adapter around the
same Python contract. It preserves the workflow described below; see
[web-development.md](web-development.md) for its implementation and setup.

## The idea that the demo must preserve

The primary user is an import or supply-chain planner at a manufacturer
that depends on imported materials. When a shipment encounters an
exception, the planner has to combine logistics information, commercial
documents, ERP records, inventory, and demand to determine what the
business should do next.

CLEAR addresses the work between receiving an exception and having an
evidence-backed recovery plan. The key requirements are:

1. Start a case from an operational event.
2. Investigate the evidence relevant to that exception.
3. Calculate the effect on material coverage and demand.
4. Assess recovery options against operational constraints.
5. Obtain human approval before a consequential enterprise write.
6. Verify the recorded action and re-plan when new information arrives.

The demo implements each of these steps within its defined scenarios.
The proposal's examples of permits, supplier problems, alternative sourcing,
and broader system integration describe a wider application of this idea;
they are not all implemented demo capabilities.

## Functional mapping

| Proposal capability | Current implementation | Alignment and boundary |
|---|---|---|
| An operational event initiates the investigation | The UI or CLI submits a prepared logistics event and starts an agent run | Implemented with simulated events; no live logistics subscription is demonstrated |
| The investigation depends on the exception | Document holds start with evidence gathering and reconciliation; congestion and ETA events start with impact assessment | Implemented within defined prompts and tool contracts; the agent's choices have explicit boundaries |
| Combine documents, shipments, purchase orders, and inventory | Read tools and document reconciliation join records by shipment, purchase order, and material | Implemented using synthetic documents and mock S/4HANA records |
| Estimate resolution time and downstream exposure | SAP-RPT-1.6 or a labelled baseline predicts duration; deterministic tools calculate coverage, shortage, cost, and deferred orders | Implemented; the prediction source is recorded |
| Compare recovery options | Assess keeping the current plan, full or partial stock transfers, and serving demand by priority | Implemented; demand prioritization is part of the current demo |
| Consider emergency sourcing | Escalate to a human when no feasible transfer can cover the required demand | Human decision boundary only; automated supplier search, sourcing, and procurement are not implemented |
| Block infeasible actions | The validator checks source safety stock, transfer timing, quantity, material, and plants | Implemented; rejection can lead to a revised option |
| Execute only permitted, approved actions | The STO tool requires a valid validation record and a matching human approval, given in the workspace or in SAP Joule; Gateway policies restrict tool access by agent role | Implemented against the mock ERP; no live SAP order creation is demonstrated |
| Verify the action and monitor the case | Check inventory after the STO and re-plan on an ETA update | Implemented as post-action verification and event-driven reassessment; a monitoring status is not proof that the physical shipment has arrived |
| Follow the incident through resolution | The plan records the next condition to check and can escalate on increased exposure | Partial: the demo does not automate customs release, document correction with external parties, or physical goods receipt |

Implementation references: [agent prompts](../src/clear_agents/prompts.py),
[recovery plan schema and checks](../src/clear_agents/plan.py),
[event handling](../src/clear_tools/events.py),
[STO creation and inventory posting](../src/clear_tools/sto.py), and the
[UI contract](ui-contract.md).

## Demo coverage and its justification

The demo has two primary scenarios and one follow-up event:

- **S1: document hold.** Shipping documents disagree on quantity. The
  agents reconcile evidence, assess exposure, validate a transfer, and
  request approval. A rejected transfer can lead to a smaller transfer
  combined with demand prioritization.
- **S1 follow-up: ETA slip.** A later arrival estimate changes the case.
  CLEAR reassesses exposure and may escalate if the existing response is
  no longer sufficient.
- **S2: port congestion.** The agents assess inventory exposure directly.
  If coverage is sufficient, they keep the current plan instead of creating
  an unnecessary transfer.

These scenarios exercise different investigation paths, action rejection,
approval, a decision to take no action, and reassessment after new evidence.
They provide a bounded demonstration of the proposal's core loop. The
proposal itself limits the prototype to one event source and one governed
write action; it does not require the prototype to automate every recovery
option mentioned in the broader concept.

Permit problems, supplier errors, and other clearance situations remain
outside the prepared demo scenarios. They should be described as possible
extensions that need additional evidence sources, rules, tools, and
evaluation. Their inclusion in the proposal is not evidence that they
already work in the demo.

See the [prepared scenarios](../src/clear_datagen/scenarios.py) and
[evaluation families](evaluation.md) for the implemented decision coverage.

## Architecture adaptations and explanations

The explanations below distinguish repository-recorded constraints from
the rationale for accepting a narrower prototype. They do not claim a
historical decision reason where the repository does not record one.

| Area | Proposal | Current documented demo | Explanation and justification |
|---|---|---|---|
| Model platform | Amazon Bedrock provides model reasoning | Claude Sonnet 4.6 in SAP AI Core; a setting can switch the model backend to Bedrock | The setup documentation records SAP AI Core access and model deployments provided for the hackathon. This is a platform adaptation: tool selection, structured plans, and validation remain part of the agent workflow. The repository does not explicitly record why AI Core was preferred over the original Bedrock plan |
| Agent hosting | AgentCore Runtime hosts the workflow | Strands agents run on the presenter's machine for the workspace, and in a Cloud Foundry app on SAP BTP for SAP Joule; both reach the tools through AgentCore Gateway | The documented constraint is the AWS account's lack of AgentCore Runtime quota. Runtime packaging exists, but that hosting configuration is not deployed. Gateway, Lambda, DynamoDB, and Cedar policies remain the deployed tool path for both |
| Planner interface | Planners and authorized decision makers review and approve recovery actions | A Next.js workspace, and SAP Joule, which calls CLEAR over A2A through a BTP destination | Joule brings the case to the SAP assistant a planner already uses; the planner writes in their own words, a decision takes effect only after confirming a preview, and the same validator, approval check, and Cedar policies apply. Joule approvals are recorded under a shared label, not per person |
| ERP integration | SAP S/4HANA Cloud supplies enterprise context and receives approved actions | Mock S/4HANA records, locally or in DynamoDB, use SAP entity and field names | The proposal explicitly permits controlled synthetic data when live SAP access is unavailable. The mock supports investigation, calculations, approval, and post-action checks without claiming a live SAP integration. This allowance does not establish the team's historical access situation |
| Event ingestion | An operational event can initiate a case | A user submits a prepared event through the demo UI or CLI | Simulating ingestion makes the prototype repeatable while preserving event-driven case execution. A live event-source integration remains to be implemented |
| Recovery actions | Broader options include transfer, emergency sourcing, prioritization, or keeping the plan | Transfer, demand-priority assessment, keeping the plan, and escalation; STO creation is the only business write tool | A single governed write is consistent with the proposal's bounded prototype. Emergency sourcing remains a human decision rather than an unimplemented capability being presented as automated |
| Duration prediction | The workflow estimates how long the exception may last | SAP-RPT-1.6 with a labelled baseline fallback | This makes the estimate's source explicit while keeping supply calculations outside the LLM |

The [architecture](architecture.md), [setup guide](setup.md), and
[project status](../README.md#status)
describe the current configuration. Presentation diagrams should match
that configuration and label future integrations separately.

## Evaluation alignment and remaining evidence

The proposal calls for a controlled comparison between a manual planner
and CLEAR on the same incident. Its metrics are recovery-plan latency,
human interventions, uncovered supply gap, and critical demand protected.

The repository has a 20-variant evaluation framework that reports those
outcomes alongside decision, priority, escalation, path, schema, and
approval checks. The final live run, on 28 October 2026 with the last
prompts, passes every check in all 20 variants.

The manual baseline is not yet a measured comparison. Its documented
93-minute total is an estimate. It must remain labelled as an estimate;
it does not support a measured percentage reduction in planner time.
Completing that experiment would close an evidence gap in the proposal's
evaluation plan, rather than change the product idea.

Use [evaluation.md](evaluation.md) as the source for results, dates,
limitations, and remaining measurement work. No new result is established
by this alignment document.

## Explanation for the presentation

> Our demo implements the proposal's core workflow: investigate an import
> exception, connect its evidence to inventory and demand exposure, assess
> recovery options, validate the action, obtain human approval, and
> reassess when the ETA changes. We bounded the prototype to document and
> port-delay cases, demand prioritization, and one governed write action:
> a stock transport order. We use synthetic SAP records, as allowed in the
> proposal. The AWS account has no AgentCore Runtime quota, so the agents
> run on the presenter's machine for the workspace and on SAP BTP Cloud
> Foundry for SAP Joule, where a planner can also approve. Model reasoning
> uses SAP AI Core, while the deployed tools use AgentCore Gateway, Lambda,
> DynamoDB, and Cedar policies. These choices adapt the implementation while
> preserving the exception-resolution workflow.

When describing the demo, make the following claims precise:

- Demand prioritization is implemented; automated emergency sourcing is
  not.
- STO creation updates the mock ERP and verifies its stock positions;
  it does not demonstrate a live SAP transaction or physical delivery.
- An ETA event can trigger re-planning; the demo does not demonstrate an
  unattended incident lifecycle through customs release and goods receipt.
- Use the live model configuration to demonstrate agent behavior. The
  scripted UI configuration is a fallback with predefined scenario
  behavior, not evidence of dynamic agent decisions.
- Report evaluation results with their run date and distinguish measured
  agent latency from the estimated manual baseline.
- Joule chooses CLEAR's skill and forwards the planner's message; Claude
  reads what the planner means, an approval or a rejection takes effect
  only after the planner confirms a preview, and Joule approvals are
  recorded under a shared label rather than the person's identity.
