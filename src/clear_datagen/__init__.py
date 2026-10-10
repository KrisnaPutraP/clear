"""Synthetic data generators (docs/PLAN.md §4). Offline only, not deployed.

generate_seed() writes the committed seed data with fixed random seeds, so
running it twice gives identical files. Every rule that shapes the data is
documented in data/README.md. The data is designed to be plausible, but it
is not real statistics (§4d).
"""

import csv
from pathlib import Path

from clear_datagen import documents, history, scenarios
from clear_tools import cases, events, planning
from clear_tools.store import JsonStore

EMPTY_RECORDS = [
    "predictions", "assessments", "validations", "approvals", "reconciliations", "stock_transport_orders",
    "cases", "case_log",
]


def generate_seed(out_dir: Path) -> None:
    """Write the complete seed data set into out_dir."""
    store = JsonStore(out_dir)
    for name, rows in scenarios.s4_entity_sets().items():
        store.write(name, rows)
    store.write(cases.SHIPMENTS, scenarios.SHIPMENTS)
    store.write(events.CATALOG, scenarios.EVENT_CATALOG)
    store.write(planning.ORDERS, scenarios.demand_orders())
    store.write(planning.PARAMETERS, scenarios.PARAMETERS)
    for name in EMPTY_RECORDS:
        store.write(f"records/{name}", [])

    for name, text in documents.render_documents().items():
        path = out_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    train, holdout = history.split(history.generate())
    for name, rows in (("exception_history_train", train), ("exception_history_holdout", holdout)):
        path = out_dir / "history" / f"{name}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=history.COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
