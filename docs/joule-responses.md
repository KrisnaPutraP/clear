# Talking to CLEAR in Joule

A planner writes to CLEAR in SAP Joule in their own words, in English or
Indonesian. Claude in SAP AI Core reads what they mean
(`src/clear_app/joule_intent.py`) with the open cases, the transfers
awaiting approval, and the prepared events as context. When the model fails,
is slow, or is unsure, keyword rules (`interpret` in
`src/clear_app/joule.py`) read the message instead.

Reading a message never changes a case. The reply is built from the
existing rendered plan and its records: no LLM writes the reply,
recalculates quantities, or changes the case. The Joule function displays
the reply with Markdown enabled and, below it, up to two buttons.

## What a planner can say

| Intent | Example messages | Effect |
|---|---|---|
| Decisions | "What needs my decision?", "anything pending?" | Lists transfers awaiting approval and cases needing a human decision |
| Case inbox | "Show the open cases", "list cases" | Reads the shared case list |
| Shipment or case status | "How is SHP-1001 doing?", "status CASE-0001" | Reads shipment facts or the latest case plan |
| Evidence and options | "Why not transfer everything?", "details of SHP-1001" | Reads the full case explanation |
| Start investigation | "Work S1-DOC-HOLD", "SHP-1002 is stuck at the port" | Submits a prepared event and starts agents |
| Hold | "Do not approve yet", "jangan approve dulu, tunggu bea cukai", "Cancel" | Changes nothing; the transfer keeps waiting |
| Approve | "Approve the transfer", "oke approve transfernya" | Shows a preview with **Confirm approval** and **Cancel** |
| Reject | "Reject it, plant 1200 needs the stock", "tolak, plant 1200 butuh stoknya" | Shows a preview with the reason, **Confirm rejection**, and **Cancel**; asks for a reason when none is given |
| Reassess an ETA change | "Work S1-ETA-SLIP" | Submits the follow-up event on the existing shipment case |

A message only needs an ID when it would otherwise be ambiguous, such as
two cases or two transfers awaiting approval; with one transfer waiting,
"approve the transfer" refers to it. The model uses only IDs that exist;
an unknown ID gets an explanatory reply. Status, details, questions, the
case inbox, and the decisions list are read-only. Starting an event begins
an investigation; it does not close a case, and the current lifecycle has
no separate closed status. Additional event IDs are listed by "help".

The demo's logistics events are prepared synthetic inputs. Submitting an
event starts live agent reasoning when the backend uses the live model; it
does not mean an external logistics subscription is connected. The
separate scripted mode, which reads messages with the keyword rules only,
is for development. Coordinate event submissions, approvals, and resets
with the presenter because data is shared.

## Decisions need a confirmation

An approval or a rejection, whether typed or pressed as a button, first
shows a preview: the transfer, the case, the recommended course, the
deferred orders, and for a rejection the reason. CLEAR issues a one-time
code with the preview. **Confirm approval** or **Confirm rejection** sends
the code back; only a message carrying the current code records the
decision, as "Planner via Joule". **Cancel**, or a message the model reads
as "hold", drops the code and changes nothing. A code expires after ten
minutes; an expired code changes nothing and lists the decisions again. A
newer preview for the same transfer replaces the code, and the old one is
no longer recognized: a message carrying it is read like any other message
and at most shows a new preview. Without buttons, the preview names the
exact confirmation text to send.

The recorded decision then goes through the same checks as from the
dashboard: the approval record, the validator's result, and the Cedar
policy at AgentCore Gateway that forbids the stock transport order without
the Action agent and an approval.

## Decisions list and case inbox

"What needs my decision?" lists each transfer awaiting approval (validation,
case, shipment, transfer, recommended course, deferred orders) and each case
needing a human decision with its reason, followed by **Approve** and
**Reject** buttons for the first transfer.

"Show the open cases" lists recorded case IDs, shipment IDs, exception
descriptions, and statuses. Human decisions appear first, followed by
approvals, active runs, and monitoring cases. Newest cases appear first
within each group. Monitoring cases remain in the list: the current
lifecycle has no separate closed status. This is the shared case inbox, not
a user-specific assignment list. Listing cases does not create a case or
start an investigation.

## Case status

Before a case exists, asking for the status of SHP-1001 shows the recorded
shipment status, purchase order, destination port, ETA, recorded
exception, and latest event. Prepared demo events are labelled separately:
they have not been submitted and are not evidence that the exception has
occurred. The reply names the next prepared event to work. Status and
details requests do not submit events, create cases, or start agents.

For a case, the reply contains:

- The case, shipment, and status.
- **Situation:** the recorded exception description.
- **Supply impact:** duration and prediction source, current coverage, and
  shortage.
- **Recommended course:** the selected option, demand priorities, transfer,
  coverage, and deferred orders. If no option is selected, the plan's
  recommendation text.
- **Approval required** or **Transfer recorded**, when the current plan
  contains an action, with **Approve** and **Reject** buttons while it
  awaits approval. Rejected transfers or actions on a case that is no
  longer awaiting approval do not offer an approval.
- **Decision required:** the full escalation text, when present.
- **Follow-up:** all next checks, with numbered points spaced for Markdown.

While a run is active, the reply shows the latest activity with **Refresh
status** and **What needs my decision?** buttons rather than a
completed-plan summary. CLEAR answers within 35 seconds because Joule waits
at most 60; a run continues in the background. A failed or planless case
retains its status reason. A recorded transfer is labelled as in transit,
not physically received.

## Detailed view

Asking for the details, or a question such as "why not transfer
everything?", adds:

- The full exception explanation and evidence with source labels.
- The original recommendation rationale.
- All assessed options, including current-plan comparison, priorities,
  coverage, transfer, deferred orders, validation, and assessment IDs.

The default view avoids repeating the full rationale and document narrative
alongside the same metrics. Full human-decision requirements and follow-up
instructions remain visible in the summary; they are not truncated.

## Rendering and deployment

Replies use bold section labels, short metric lists, inline code, and
numbered follow-ups. Buttons travel as a second A2A artifact with one data
part (a title, a primary and a secondary button); the Joule function in
`joule/clear_capability/functions/ask_clear.yaml` renders them as postback
buttons, which send their text back to Joule as the planner's next message.
Exact styling depends on Joule's renderer. These replies are not the
Next.js dashboard; Next.js reads structured data through FastAPI.

Calculations, agent prompts, and approval requirements are unchanged by
this conversation layer. The A2A server logs each incoming message with how
it was read. Backend changes require an A2A backend deployment; capability
or destination changes require the corresponding Joule configuration
update as well. Editing local files alone does not change the deployed
assistant. Account-specific deployment settings and credentials are kept
outside this public guide.
