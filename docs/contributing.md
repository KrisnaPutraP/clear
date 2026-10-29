# Working on CLEAR

How the team works on this repository: the rules the code keeps, how to
change each part safely. For the demo, current status, and prototype
boundaries, start with the [README](../README.md). Developer setup:
[setup.md](setup.md).

## The design rule

**The LLM proposes, code computes and validates, a human approves.**

- Business numbers never come from the LLM. Durations come from SAP-RPT-1.6
  or the baseline; stock, coverage, shortage, cost, and feasibility come from
  the deterministic tools.
- Every number shows its source: each prediction carries a `source` field,
  and the case log names the tool behind each step.
- A demo that works every time beats a demo with more features. Add a
  feature, a component, or a dependency only when the team agrees.

## Code rules

- **Tools take IDs and decisions, never business numbers.** A tool reads
  stock from the data itself; predictions are cited by `prediction_id`; an
  STO is created from a `validation_id` and an `approval_id`.
- **`src/clear_tools/` is standard library only**, so it runs and is tested
  without AWS and the Lambda function wraps it unchanged
  (`tests/test_architecture.py` enforces this).
- **English** for code, comments, data, documents, UI text, and agent output.
- **No secrets in Git, logs, or chats.** `.env` holds them locally.
- **Check APIs in the official documentation** (S/4HANA field names, Strands,
  AgentCore, SAP AI Core) rather than from memory, and say so when it cannot
  be confirmed.
- **The synthetic data's rules are documented** in
  [data/README.md](../data/README.md); the data are not real statistics.

## Before every commit

```
pytest
```

All tests pass, including the S1 and S2 invariants in `tests/scenarios/`,
which must hold whenever data or logic changes. Commit messages: a short
imperative subject, then a body that explains why the change was made.

## Changing the agents

The agents' behaviour lives in `src/clear_agents/prompts.py` (the four system
prompts), `src/clear_agents/plan.py` (the recovery plan schema and the plan
checks), and the tool descriptions in `src/clear_agents/tools.py`; the model
reads all three.

1. Run the affected scenario live: `python scripts/run_scenario.py S1 --approve --eta-slip`
   or `S2`.
2. Run the evaluation variants the change can affect, for example
   `python scripts/run_eval.py --variants C1,C2,C3,C4` (about two minutes
   each). [evaluation.md](evaluation.md) explains the families.
3. Before the feature freeze, run all 20 variants once and record the result
   in [evaluation.md](evaluation.md); the pitch quotes those numbers.

The oracle (`src/clear_eval/oracle.py`) is the reference for what the agents
should decide; when the prompts and the oracle disagree, the prompts change.

## Changing tools or data

- Tool logic is in `src/clear_tools/`. Its tests are in `tests/`: the S1 and S2
  invariants, governance (validation, approval, STO), reconciliation, and
  prediction.
- The seed is generated: change `src/clear_datagen/`, run
  `python scripts/generate_seed.py`, and update
  [data/README.md](../data/README.md) when a rule changes.
- `docs/examples/case_s1.json` is the UI contract's example;
  `scripts/make_ui_example.py` regenerates it.

## Changing what runs on AWS

Only the account owner deploys, and nothing on AWS is created, changed, or
deleted without the owner's agreement.

- Code reaches AWS only through `scripts/build_deploy.py` followed by
  `agentcore deploy` ([deployment.md](deployment.md)).
- After any change to the Cedar policies, run `python scripts/check_policies.py`.
- AWS resources are in us-west-2, named with the prefix `cookusan-hackathon`
  (or `cookusanhackathon` where the AgentCore CLI names them), and tagged
  `Project=ID-Hackathon-2026`, `Team=Cookusan`, `DeleteAfter=2026-10-31`.
- No NAT gateways, GPUs, always-on endpoints, or high-volume logging.

## Changing Joule responses

Message routing and Markdown presentation live in `src/clear_app/joule.py`.
Keep case-list, status, and details requests read-only. Approval must keep
its explicit validation ID and use the shared contract's existing checks.
Update [joule-responses.md](joule-responses.md) when commands or visible
behavior change. These replies do not replace the structured FastAPI data
used by Next.js.

Run the full test suite before committing; `tests/test_joule.py` covers
command routing and the A2A conversation with an isolated synthetic store.
Live SAP/AWS checks are separate from offline tests. A backend deployment
is needed for updated replies; capability and destination changes have
their own Joule deployment step.

Do not run independent case-writing processes against the shared demo
store concurrently. The service's busy lock is process-local, so starting
FastAPI beside the deployed A2A service does not provide a shared lock.

## Private documents

`docs/PLAN.md` (the locked design decisions), `docs/pitch.md` (the pitch
draft), and `docs/reference/` (hackathon brief, slides, proposal) stay out of
Git; the team shares them privately. `docs/joule.md` contains private
operating notes and is excluded locally via `.git/info/exclude`. Keep
account URLs, credentials, login workarounds, and generated deployment
archives out of new public documentation. Docstrings cite sections of the
plan as
`docs/PLAN.md §…`. Material from `docs/reference/`, especially slides marked
internal, is never copied into the repository; summarize it in your own
words where needed.
