"""Records that chain the governed write path (docs/PLAN.md §5a, §6).

Predictions, validations, and approvals each get a readable sequential ID.
A later step references an earlier result by that ID instead of an LLM
retyping its numbers: an STO is created from a validation_id plus an
approval_id, and its quantity is read from the validation record.
"""

from datetime import datetime, timezone

from clear_tools.store import JsonStore

_PREFIX = {"prediction": "PRED", "validation": "VAL", "approval": "APR"}


def add(store: JsonStore, kind: str, record: dict) -> dict:
    """Store a new record of the given kind and return it with its ID."""
    name = f"records/{kind}s"
    items = store.read(name)
    stored = {f"{kind}_id": f"{_PREFIX[kind]}-{len(items) + 1:04d}", **record, "created_at": now()}
    items.append(stored)
    store.write(name, items)
    return stored


def get(store: JsonStore, kind: str, record_id: str) -> dict:
    for item in store.read(f"records/{kind}s"):
        if item[f"{kind}_id"] == record_id:
            return item
    raise LookupError(f"Unknown {kind}_id: {record_id}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
