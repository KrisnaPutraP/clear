# Joule response format

The A2A server formats a case from the existing rendered plan. It does not
ask an LLM to rewrite the reply, recalculate quantities, or change the case.
The Joule function already displays that text with Markdown enabled.

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

The formatter is in `src/clear_app/joule.py`; routing, calculations, agent
prompts, and approval requirements remain in their existing components.
After reviewing and merging the change, the running A2A backend must be
updated for Joule to show the new output. Editing local files alone does
not change an already deployed server. No destination or credentials need
to be included in this public formatting guide.
