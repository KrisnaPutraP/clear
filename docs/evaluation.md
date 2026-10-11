# Evaluating CLEAR

Two questions: does CLEAR make the right call on cases it was not scripted
for, and how much faster is it than doing the work by hand?

## Reliability batch

Twenty variants of the same seed (`src/clear_eval/variants.py`) change
stock and safety stock so that each one needs a different decision. For
each variant, an oracle (`src/clear_eval/oracle.py`) computes the right
decision with the same deterministic tools the agents use:

1. Predict the resolution time and assess the current plan. If it is
   covered, keep the plan.
2. Otherwise validate a transfer of the whole shortage from the plant with
   the most stock above safety stock. If it passes, transfer.
3. Otherwise, with a feasible partial quantity, serve fewer orders by
   priority until one level is covered: transfer and prioritize.
4. With no feasible transfer, serve fewer orders without one and escalate
   the deferred orders to a human; if even critical orders are not covered,
   escalate.

| Family | Variants | Right decision |
|---|---|---|
| Document exception, transfer and prioritize | A1-A4 | Partial transfer, critical (+ high) orders only |
| Document exception, transfer | B1-B3 | Transfer the whole shortage |
| Document exception, no feasible transfer | C1-C4 | Prioritize and escalate, or escalate |
| Document exception, enough stock | D1-D3 | Keep the plan |
| Port congestion, covered | E1-E3 | Keep the plan |
| Port congestion, shortage | F1-F3 | Transfer, transfer and prioritize, or escalate |

The arithmetic is guaranteed by code, so the batch scores the agents'
choices. Each variant passes or fails these checks:

| Check | Passes when |
|---|---|
| `decision_correct` | The plan's decision class matches the oracle |
| `priority_correct` | The decision and the order priority level both match |
| `escalation_correct` | The plan escalates exactly when the oracle says a human must decide |
| `right_path` | A document exception is reconciled before impact is quantified; a congestion event starts from inventory exposure |
| `no_write_without_approval` | No stock transport order exists before a human approves |
| `schema_valid` | The plan parses and every ID it cites exists for this shipment |
| `critical_protected` | The recommended plan never defers a critical order |

The batch also reports the proposal's four metrics: median time to a
recovery plan, human interventions (approvals and escalations), uncovered
supply gap before and after the recommended plans, and critical demand
protected. Evaluation runs use the baseline prediction so the ground truth
is stable; SAP-RPT-1.6 is evaluated on its own
(`scripts/check_rpt_quality.py`).

Run it:

```
python scripts/run_eval.py              # all variants, agents on the live model (CLEAR_LLM_BACKEND)
python scripts/run_eval.py --scripted   # plumbing check without AWS (A1, E1)
```

Reports are written to `data/eval/` as JSON and Markdown.

## Manual baseline (scenario S1)

The comparison counts the steps a planner takes today, from the process in
the original proposal. **The minutes are estimates, not measurements**, and
are labelled as such wherever they are shown.

| # | Manual step | Estimate (min) |
|---|---|---|
| 1 | Open the shipment and read the exception notice | 5 |
| 2 | Find the purchase order in the ERP | 3 |
| 3 | Collect the four shipping documents | 10 |
| 4 | Compare the documents with each other and with the PO | 15 |
| 5 | Work out days of coverage per order priority | 15 |
| 6 | Check stock and safety stock at the other plant | 5 |
| 7 | Work out a feasible transfer and which orders to defer | 15 |
| 8 | Ask for approval (excluding the approver's waiting time) | 15 |
| 9 | Create the stock transport order | 5 |
| 10 | Verify stock positions | 5 |
| | **Total** | **93** |

CLEAR replaces steps 1-7, 9, and 10 with agent work that the timeline
makes reviewable, and leaves one human step: the approval. A builder who
already knows the answer can time S1 by hand once with a stopwatch; that
time is a lower bound, which keeps the claim conservative.
