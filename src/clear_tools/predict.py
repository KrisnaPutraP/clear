"""predict_resolution_time (docs/PLAN.md §3, §5a).

Predicts how many days an exception will take to resolve. One tool contract
with interchangeable backends; every prediction gets a prediction_id and a
source label naming the backend that produced the number.

- Level 0, "sap-rpt-1.6": SAP-RPT-1.6 on SAP AI Core learns from past
  exceptions of the same type (in-context learning) and returns a confidence
  interval plus the past cases it found most relevant.
- Level 2, "baseline-median": the median resolution time of past exceptions
  with the same type, port, and congestion level. Groups with too few cases
  fall back to type and port, then to type alone.

CLEAR_PREDICTION_BACKEND=auto tries Level 0 first and falls back to Level 2
on any error or timeout, recording why (§3c). Unset or "baseline" uses Level 2
only, which keeps tests offline and deterministic. Level 1 (sap-rpt-1-oss) is
not built: SAP AI Core access arrived before the 17 October cut-off.
"""

import os
import statistics
import time
from datetime import datetime

from clear_tools import cases, planning, records, sap_rpt
from clear_tools.store import JsonStore

HISTORY = "history/exception_history_train.csv"
TARGET = "resolution_days"
BASELINE = "baseline-median"
RPT = "sap-rpt-1.6"

BACKEND_SETTING = "CLEAR_PREDICTION_BACKEND"
TIMEOUT_SETTING = "CLEAR_RPT_TIMEOUT_SECONDS"
DEFAULT_TIMEOUT_SECONDS = 15.0
MIN_CONTEXT_ROWS = 50  # Below this, RPT learns from all past exceptions, not only the same type.
SIMILAR_CASES = 8

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
    rows = store.read_csv(HISTORY)

    prediction, fallback_reason = None, None
    if os.environ.get(BACKEND_SETTING, "baseline").strip().lower() == "auto":
        try:
            prediction = _rpt_prediction(rows, features)
        except Exception as error:  # Any failure falls back to the baseline, with the reason recorded.
            fallback_reason = f"{type(error).__name__}: {error}"
    if prediction is None:
        prediction = _baseline_prediction(rows, features, planning.baseline_min_group_size(store))
        if fallback_reason:
            prediction["basis"]["fallback_reason"] = fallback_reason

    return records.add(store, "prediction", {
        "shipment_id": shipment_id, **prediction, "features": features, "drivers": None,
    })


def baseline_median(
    rows: list[dict[str, str]], features: dict[str, str], min_cases: int
) -> tuple[float, dict[str, str], int]:
    """Median resolution days of past exceptions like this one, the grouping used, and its size."""
    for keys in GROUPINGS:
        days = [float(row[TARGET]) for row in rows if all(row[k] == features[k] for k in keys)]
        if len(days) >= min_cases:
            return round(statistics.median(days), 1), {k: features[k] for k in keys}, len(days)
    raise LookupError(f"Fewer than {min_cases} past cases of {features['exception_type']}")


def _baseline_prediction(rows: list[dict[str, str]], features: dict[str, str], min_cases: int) -> dict:
    days, grouped_by, count = baseline_median(rows, features, min_cases)
    return {
        "predicted_days": days,
        "source": BASELINE,
        "basis": {"method": "median resolution_days of similar past exceptions",
                  "grouped_by": grouped_by, "cases": count},
    }


def _rpt_prediction(rows: list[dict[str, str]], features: dict[str, str]) -> dict:
    config = sap_rpt.Config.from_env()
    timeout = float(os.environ.get(TIMEOUT_SETTING, DEFAULT_TIMEOUT_SECONDS))
    started = time.monotonic()
    token = sap_rpt.access_token(config, timeout=timeout)
    same_type = [row for row in rows if row["exception_type"] == features["exception_type"]]
    context = same_type if len(same_type) >= MIN_CONTEXT_ROWS else rows
    remaining = max(1.0, timeout - (time.monotonic() - started))
    [result] = sap_rpt.predict(
        config, context, [features], TARGET, token=token, explain_rows=SIMILAR_CASES, timeout=remaining
    )
    similar = [context[i] for i in result.similar_rows or []]
    return {
        "predicted_days": round(result.value, 1),
        "source": RPT,
        "basis": {
            "method": "SAP-RPT-1.6 in-context prediction from past exceptions",
            "context_cases": len(context),
            "interval_days": [round(bound, 1) for bound in result.interval] if result.interval else None,
            "similar_cases": [
                {k: row[k] for k in ("exception_type", "port", "congestion_level", TARGET)} for row in similar
            ],
            "latency_seconds": round(time.monotonic() - started, 1),
        },
    }


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
