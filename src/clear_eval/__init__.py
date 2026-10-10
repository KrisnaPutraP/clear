"""Evaluation harness for the CLEAR agents (docs/PLAN.md §9b, §9c).

Twenty scenario variants come from the same seed with different stock,
safety stock, and events. For each one, an oracle computes the right
decision from the business rules with the deterministic tools; the agents
then work the variant and their plan is scored against it. The arithmetic
is guaranteed by code, so the harness scores the agents' choices: the
decision, the path, validation before any write, and escalation.
"""
