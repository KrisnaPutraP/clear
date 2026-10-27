# CLEAR UI contract

A front end for CLEAR needs four operations plus two lists (prepared events
and cases). They are methods of `clear_app.contract.Clear` (Python,
used by the Streamlit app in `app/streamlit_app.py`) and HTTP routes in
`clear_app.api`. The Next.js workspace in `frontend/` uses these routes
through its `/api/clear/*` proxy. See [web-development.md](web-development.md)
for startup, configuration, and the single-worker constraint.

[`examples/case_s1.json`](examples/case_s1.json) holds the exact output of
every call during scenario S1: the exception, the planner's approval, and the
ETA slip. You can build screens before the agents run on the cloud. The agent
wording in it is illustrative; the shapes are exact.

## Calls

| Call | Python | HTTP | Returns |
|---|---|---|---|
| List prepared events | `list_events()` | `GET /events` | `[{event_id, scenario, type, shipment_id, description}]` |
| List cases | `list_cases()` | `GET /cases` | `[{case_id, shipment_id, status}]`, newest first |
| Send an event | `send_event(event_id)` | `POST /events/{event_id}` | `case_id`; the agents keep working in the background |
| Read a case | `get_case(case_id)` | `GET /cases/{case_id}` | Status, shipment, documents, stock, and the plan with all numbers filled in |
| Read the timeline | `get_case_log(case_id, after_seq=0)` | `GET /cases/{case_id}/log?after_seq=N` | Log entries with `seq` greater than `N` |
| Decide on an STO | `submit_decision(case_id, validation_id, approver, decision, reason=None)` | `POST /cases/{case_id}/decisions` | The approval record |

`decision` is `approved` or `rejected`; a rejection needs a `reason`. Only
one agent run happens at a time: while `get_case(...)["running"]` is true,
`send_event` and `submit_decision` fail with "An agent run is in progress".

Event and decision POSTs return HTTP `202` without waiting for the agents.
The event response is `{"case_id": "CASE-..."}`; the decision response is
the approval record. A rejection records its decision synchronously and
starts no agent run. Approval requests must target an action that is
awaiting approval on the current case plan. A stale or unrelated validation
is rejected before an approval record is written.

Unknown IDs return `404`, conflicting runs or decisions return `409`, and
invalid request bodies or negative log cursors return `422`. Decision
bodies contain `validation_id`, `approver`, `decision`, and optional
`reason`; a rejection requires a nonblank reason.

`GET /health` additionally reports the configured mode/model/prediction,
synthetic-data indicator, process status, and global `running` flag. It
does not test upstream SAP or AWS availability. Interactive API documentation
is available at `/docs`.

## Live timeline

While `running` is true, call `get_case_log(case_id, after_seq=<last seq
you have>)` every one or two seconds and append what comes back. When
`running` turns false, call `get_case` once for the final status and plan.

## Case status

| `status` | Meaning | What to show |
|---|---|---|
| `analyzing` | Agents are working on a new event | Timeline |
| `awaiting_approval` | A validated stock transport order waits for a planner | Approval card |
| `executing` | Approved; the order is being created | Timeline |
| `monitoring` | The plan is in place and nothing needs a decision | Plan and `next_check` |
| `needs_human_decision` | Rejected, escalated, or the run failed | `status_reason`, options |

## Timeline entries

`{seq, case_id, at, actor, kind, summary, tool?, source?, flag?, event_id?, approval_id?}`

- `actor`: `Event feed`, `Orchestrator`, `Evidence`, `Impact & Options`,
  `Action`, the planner's name, `Plan check`, or `CLEAR`.
- `kind`: `event`, `delegation`, `tool`, `note` (a short reason written by an
  agent), `approval`, `status`, or `error`.
- `source`: where the numbers in `summary` come from, for example
  `baseline-median`, `S/4HANA (mock)`, `deterministic calculation`, or
  `business rules`. Show it next to the summary.
- `flag`: `rejected` (the validator refused an action; make it stand out),
  `discrepancy` (documents disagree), `write` (an ERP write), or `error`.

## Case extras

Besides the status and plan, `get_case` returns what the side panels need:

- `documents`: `{required_documents, documents: [{document_type, text}]}`.
- `reconciliation`: the latest document check, or `null`. Each entry of
  `discrepancies` names a `field` and its `mismatched_documents`;
  `verified_extractions` holds the exact `quote` each value was read from, so
  you can highlight the line that differs (and the agreeing line in the
  other documents for comparison).
- `inventory`: stock, stock in transit, safety stock, and daily use at each
  priority level, per plant.

## Plan

Every number in the plan comes from a stored tool result, never from the
model's text.

- `impact`: `prediction` (`predicted_days`, `source`, `basis`), and
  `coverage_days`, `required_coverage_days`, `shortage_t`, `covered` for the
  current plan.
- `options[]`: `name`, `note`, and `assessment` (`priority_level`,
  `transfer`, `coverage_days`, `required_coverage_days`, `covered`,
  `shortage_t`, `deferred_orders`), plus `validation` when the option has a
  transfer.
- `actions[]`: `validation_id`, `status` (`awaiting_approval` or
  `executed`), `validation` (`quantity`, `source_plant`,
  `destination_plant`, `valid`, `violations`), `approval`, and `sto`.
- `verification`: stock per plant after an executed order.
- `recommendation`, `recommended_option`, `escalation`, `next_check`: short
  text written by the agent.

The approval card shows `recommendation`, the numbers of the recommended
option, and the action's `validation`, with Approve and Reject buttons;
Reject asks for a reason.
