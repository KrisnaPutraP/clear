# Joule commands and case responses

The A2A server formats a case from the existing rendered plan. It does not
ask an LLM to rewrite the reply, recalculate quantities, or change the case.
The Joule function already displays that text with Markdown enabled.

## Commands

| Intent | Example | Effect |
|---|---|---|
| Help | `help` | Lists commands and prepared events |
| Case inbox | `show open cases`, `show cases`, `list cases` | Reads the shared case list |
| Shipment or case status | `status of SHP-1001`, `status CASE-0001` | Reads shipment facts or the latest case plan |
| Evidence and options | `details of SHP-1001`, `details CASE-0001` | Reads the full case explanation |
| Start investigation | `work S1-DOC-HOLD` | Submits a prepared event and starts agents |
| Approve transfer | `approve VAL-xxxx` | Records approval and starts the STO execution run |
| Reject transfer | `reject VAL-xxxx because <reason>` | Records rejection and requests a human decision |
| Reassess an ETA change | `work S1-ETA-SLIP` | Submits the follow-up event on the existing shipment case |

Use actual case and validation IDs from the reply. The parser recognizes
keywords and IDs, not unrestricted natural-language intent. For example,
`check status SHP-1001` is accepted. Approvals must name the validation;
rejections also need a reason. Status, details, and inbox requests are
read-only. `work` starts handling an event, not closing the case. The current
lifecycle has no separate closed status. Additional event IDs are listed
by `help`.

The demo's logistics events are prepared synthetic inputs. Submitting an
event starts live agent reasoning when the backend uses the live model;
it does not mean an external logistics subscription is connected. The
separate scripted mode is for development. Coordinate event submissions,
approvals, and resets with the presenter because data is shared.

## Case inbox

Ask `show open cases`, `show cases`, or `list cases` to see recorded case
IDs, shipment IDs, exception descriptions, and statuses. Human decisions
appear first, followed by approvals, active runs, and monitoring cases.
Newest cases appear first within each group. Monitoring cases remain in
the list: the current lifecycle has no separate closed status. These
commands show the shared case inbox, not a user-specific assignment list.
Listing cases does not create a case or start an investigation.

## Case status

Before a case exists, `status of SHP-1001` shows the recorded shipment
status, purchase order, destination port, ETA, recorded exception, and
latest event. Prepared demo events are labelled separately: they have not
been submitted and are not evidence that the exception has occurred. The
reply offers `work <event ID>` to submit the next prepared event and begin
analysis. Status and details requests do not submit events, create cases,
or start agents. Unknown shipment or case IDs return an explanatory reply.

Ask `status of SHP-1001` or `status CASE-0001`. The reply contains:

- The case, shipment, and status.
- **Situation:** the recorded exception description.
- **Supply impact:** duration and prediction source, current coverage, and
  shortage.
- **Recommended course:** the selected option, demand priorities, transfer,
  coverage, and deferred orders. If no option is selected, preserve the
  plan's recommendation text.
- **Approval required** or **Transfer recorded**, when the current plan
  contains an action. Approval commands name the validation explicitly.
  Rejected transfers or actions on a case that is no longer awaiting
  approval do not offer an active approval command.
- **Decision required:** the full escalation text, when present.
- **Follow-up:** all next checks, with numbered points spaced for Markdown.

While a run is active, show the latest activity and a status command rather
than a completed-plan summary. A failed or planless case retains its status
reason. A recorded transfer is labelled as in transit, not physically
received.

## Detailed view

Ask `details CASE-0001` or `details of SHP-1001`. This adds:

- The full exception explanation and evidence with source labels.
- The original recommendation rationale.
- All assessed options, including current-plan comparison, priorities,
  coverage, transfer, deferred orders, validation, and assessment IDs.

The default view avoids repeating the full rationale and document narrative
alongside the same metrics. Full human-decision requirements and follow-up
instructions remain visible in the summary; they are not truncated.

## Rendering and deployment

Replies use bold section labels, short metric lists, inline-code commands,
and numbered follow-ups. These are text messages, not the Next.js dashboard
or interactive Joule cards. Exact styling depends on Joule's renderer.

Routing and response formatting are in `src/clear_app/joule.py`.
Calculations, agent prompts, and approval requirements are unchanged by
this presentation layer. Next.js reads structured data through FastAPI;
it does not consume this Markdown response.

Backend command and format changes require an A2A backend deployment.
Capability or destination changes require the corresponding Joule
configuration update as well. Editing local files alone does not change
the deployed assistant. Account-specific deployment settings and
credentials are kept outside this public guide.
