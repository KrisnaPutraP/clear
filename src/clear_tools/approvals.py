"""Human approval records (docs/PLAN.md §6b, §6c).

Not an agent tool: only the approval card in the UI calls this. Each
approval is bound to one validation_id, only a passing validation can be
approved, and a rejection must state its reason.
"""

from clear_tools import records
from clear_tools.store import JsonStore

DECISIONS = ("approved", "rejected")


def record_approval(
    store: JsonStore, validation_id: str, approver: str, decision: str, reason: str | None = None
) -> dict:
    """Record a planner's decision on a validation and return it with its approval_id."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {list(DECISIONS)}, got {decision!r}")
    if not approver:
        raise ValueError("approver is required")
    if decision == "rejected" and not reason:
        raise ValueError("A rejection needs a reason")
    validation = records.get(store, "validation", validation_id)
    if decision == "approved" and not validation["valid"]:
        raise PermissionError(f"{validation_id} failed validation and cannot be approved.")
    return records.add(store, "approval", {
        "validation_id": validation_id,
        "approver": approver,
        "decision": decision,
        "reason": reason,
    })
