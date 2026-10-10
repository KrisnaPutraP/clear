"""predict_resolution_time (docs/PLAN.md §3, §5a).

Predicts how many days an exception will take to resolve. One tool contract
with interchangeable backends; every prediction gets a prediction_id and a
source label: sap-rpt-1.6, sap-rpt-1-oss, or baseline-median.

MVP item 1 builds only the Level 2 backend: the median resolution time of
past exceptions with the same type, port, and congestion level, taken from
the exception history table. Groups with too few cases fall back to type and
port, then to type alone. The SAP backends (Levels 0 and 1) and the automatic
fallback chain come with MVP item 5.
"""

import statistics
from datetime import datetime

from clear_tools import cases, planning, records
from clear_tools.store import JsonStore

HISTORY = "history/exception_history_train.csv"
SOURCE = "baseline-median"

GROUPINGS = (
    ("exception_type", "port", "congestion_level"),
    ("exception_type", "port"),
    ("exception_type",),
)


def predict_resolution_time(store: JsonStore, shipment_id: str) -> dict:
    """Predict resolution days for the shipment's current exception."""
    case = cases.case(store, shipment_id)
    exception = case.shipment.get("exception")
    if not exception:
        raise ValueError(f"{shipment_id} has no active exception to predict")
    features = _features(case, exception)

    days, grouped_by, cases_used = baseline_median(
        store.read_csv(HISTORY), features, planning.baseline_min_group_size(store)
    )
    return records.add(store, "prediction", {
        "shipment_id": shipment_id,
        "predicted_days": days,
        "source": SOURCE,
        "basis": {
            "method": "median resolution_days of similar past exceptions",
            "grouped_by": grouped_by,
            "cases": cases_used,
        },
        "features": features,
        "drivers": None,
    })


def baseline_median(
    rows: list[dict[str, str]], features: dict[str, str], min_cases: int
) -> tuple[float, dict[str, str], int]:
    """Median resolution days of past exceptions like this one, the grouping used, and its size."""
    for keys in GROUPINGS:
        days = [float(row["resolution_days"]) for row in rows if all(row[k] == features[k] for k in keys)]
        if len(days) >= min_cases:
            return round(statistics.median(days), 1), {k: features[k] for k in keys}, len(days)
    raise LookupError(f"Fewer than {min_cases} past cases of {features['exception_type']}")


def _features(case: cases.Case, exception: dict) -> dict[str, str]:
    """Exception attributes in the format of the history table (docs/PLAN.md §4d)."""
    shipment = case.shipment
    return {
        "exception_type": exception["exception_type"],
        "port": case.port,
        "cargo_category": shipment["cargo_category"],
        "missing_documents": str(exception["missing_documents"]),
        "has_document_discrepancy": "true" if exception["has_document_discrepancy"] else "false",
        "congestion_level": exception["congestion_level"],
        "forwarder": shipment["forwarder"],
        "origin_country": shipment["origin_country"],
        "month": str(datetime.fromisoformat(exception["raised_at"]).month),
    }
