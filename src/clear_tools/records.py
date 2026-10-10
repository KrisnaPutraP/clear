"""Records that chain the governed write path (docs/PLAN.md §5a, §6).

Predictions, assessments, validations, and approvals each get a readable
sequential ID. A later step references an earlier result by that ID instead
of an LLM retyping its numbers: an STO is created from a validation_id plus
an approval_id, and a recovery plan cites assessment_ids for its options.
Cases use the same mechanism.
"""

from datetime import datetime, timezone

from clear_tools.store import JsonStore

_PREFIX = {"prediction": "PRED", "assessment": "ASM", "validation": "VAL", "approval": "APR",
           "reconciliation": "REC", "case": "CASE"}


def add(store: JsonStore, kind: str, record: dict) -> dict:
    """Store a new record of the given kind and return it with its ID."""
    name = f"records/{kind}s"
    items = store.read(name)
    stored = {f"{kind}_id": next_id(store, kind), **record, "created_at": now()}
    items.append(stored)
    store.write(name, items)
    return stored


def next_id(store: JsonStore, kind: str, ahead: int = 1) -> str:
    """The ID that the ahead-th next record of this kind will get."""
    return f"{_PREFIX[kind]}-{len(store.read(f'records/{kind}s')) + ahead:04d}"


def get(store: JsonStore, kind: str, record_id: str) -> dict:
    for item in store.read(f"records/{kind}s"):
        if item[f"{kind}_id"] == record_id:
            return item
    raise LookupError(f"Unknown {kind}_id: {record_id}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
