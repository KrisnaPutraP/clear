"""CLEAR tool logic as a pure Python package (docs/PLAN.md §5b).

Standard library only, so every tool runs and is tested locally without an AWS
account. At deploy time, thin Lambda handlers wrap these functions behind
AgentCore Gateway; this package never imports an AWS SDK.

Contract rule (§5a): deterministic tools take only IDs and decision variables
and read business numbers from the data store themselves. Predictions are
referenced by prediction_id; an STO is created from a validation_id plus an
approval_id.
"""
