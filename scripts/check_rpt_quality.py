"""Quality check of SAP-RPT-1.6 against the Level 2 baseline (docs/PLAN.md §3c).

Pass criteria:
1. RPT's error on the held-out history rows is not worse than the baseline's.
2. With RPT predictions, S1 and S2 still land on the right side of the
   coverage thresholds (the same story the invariant tests guard).
3. RPT's explanations make business sense. Printed for human review: the
   past cases RPT found most relevant for each scenario, and the average
   weight per column (attention, not cause and effect; origin_country and
   month have no direct effect by design).

Needs the SAP AI Core settings in .env (see .env.example).
Usage: python scripts/check_rpt_quality.py
"""

import csv
import os
import statistics
import tempfile
from collections import defaultdict
from pathlib import Path

from clear_tools import records, sap_rpt
from clear_tools.approvals import record_approval
from clear_tools.events import prepared_event, record_event
from clear_tools.predict import GROUPINGS, baseline_median, predict_resolution_time
from clear_tools.sto import create_stock_transport_order
from clear_tools.store import JsonStore, reset_runtime
from clear_tools.supply_risk import calculate_supply_risk
from clear_tools.validate import validate_action

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = REPO_ROOT / "data" / "seed"
TARGET = "resolution_days"
MIN_CASES = 10  # Same as planning/parameters.json.
SIMILAR_CASES = 8


def main() -> None:
    load_env(REPO_ROOT / ".env")
    config = sap_rpt.Config.from_env()
    token = sap_rpt.access_token(config)
    train = read_rows("exception_history_train")
    holdout = read_rows("exception_history_holdout")

    queries = [{k: v for k, v in row.items() if k != TARGET} for row in holdout]
    rpt = sap_rpt.predict(config, train, queries, TARGET, token=token, explain_columns=9, timeout=180)
    actual = [float(row[TARGET]) for row in holdout]
    baseline = [baseline_median(train, row, MIN_CASES)[0] for row in holdout]
    rpt_mae = statistics.mean(abs(p.value - a) for p, a in zip(rpt, actual))
    baseline_mae = statistics.mean(abs(b - a) for b, a in zip(baseline, actual))
    print(f"1. Holdout ({len(holdout)} rows), mean absolute error in days:")
    print(f"   baseline-median {baseline_mae:.3f}   sap-rpt-1.6 {rpt_mae:.3f}   "
          f"-> {'PASS' if rpt_mae <= baseline_mae else 'FAIL'}")

    checks, similar = check_story(config, token, train)
    print("2. Scenario story with RPT predictions:")
    for name, passed in checks.items():
        print(f"   {'PASS' if passed else 'FAIL'}  {name}")

    print(f"3a. The {SIMILAR_CASES} past cases RPT found most relevant (review):")
    group = GROUPINGS[0]
    for name, (features, rows) in similar.items():
        matching = sum(all(r[k] == features[k] for k in group) for r in rows)
        days = sorted(float(r[TARGET]) for r in rows)
        print(f"   {name:<8} {matching}/{len(rows)} share {', '.join(features[k] for k in group)}; "
              f"resolved in {days[0]}-{days[-1]} days")
    print("3b. Average weight per column on the holdout (attention, not cause and effect):")
    weights = defaultdict(list)
    for prediction in rpt:
        for column, score in (prediction.column_scores or {}).items():
            weights[column].append(score)
    for column, scores in sorted(weights.items(), key=lambda kv: -statistics.mean(kv[1])):
        print(f"   {column:<26} {statistics.mean(scores):.3f}")


def check_story(config: sap_rpt.Config, token: str, context: list[dict]):
    """Run S1 and S2 with RPT predictions; return the checks and RPT's similar past cases."""
    similar = {}
    with tempfile.TemporaryDirectory() as tmp:
        store = JsonStore(Path(tmp) / "runtime")
        reset_runtime(SEED_DIR, store.root)

        def rpt_prediction(shipment_id: str, name: str) -> dict:
            features = predict_resolution_time(store, shipment_id)["features"]  # Baseline record gives the features.
            [result] = sap_rpt.predict(
                config, context, [features], TARGET, token=token, explain_rows=SIMILAR_CASES, timeout=60
            )
            similar[name] = (features, [context[i] for i in result.similar_rows or []])
            return records.add(store, "prediction", {
                "shipment_id": shipment_id, "predicted_days": round(result.value, 1),
                "source": "sap-rpt-1.6", "basis": {"interval": result.interval}, "features": features,
                "drivers": None,
            })

        record_event(store, prepared_event(store, "S1-DOC-HOLD"))
        first = rpt_prediction("SHP-1001", "S1")
        all_orders = calculate_supply_risk(store, "SHP-1001", first["prediction_id"])
        full = validate_action(store, "SHP-1001", first["prediction_id"], "1200", all_orders["shortage_t"])
        partial = full["max_feasible_quantity"]
        prioritized = calculate_supply_risk(store, "SHP-1001", first["prediction_id"], "critical_high", partial, "1200")
        approved = validate_action(store, "SHP-1001", first["prediction_id"], "1200", partial)
        approval = record_approval(store, approved["validation_id"], "Quality check", "approved")
        create_stock_transport_order(store, approved["validation_id"], approval["approval_id"])

        record_event(store, prepared_event(store, "S1-ETA-SLIP"))
        slipped = rpt_prediction("SHP-1001", "S1 slip")
        critical_high = calculate_supply_risk(store, "SHP-1001", slipped["prediction_id"], "critical_high")
        critical = calculate_supply_risk(store, "SHP-1001", slipped["prediction_id"], "critical")

        record_event(store, prepared_event(store, "S2-CONGESTION"))
        contrast = rpt_prediction("SHP-1002", "S2")
        s2 = calculate_supply_risk(store, "SHP-1002", contrast["prediction_id"])

    checks = {
        f"S1 shortage exceeds the feasible transfer (prediction {first['predicted_days']} d)":
            all_orders["shortage_t"] > partial > 0 and not full["valid"],
        "S1 partial transfer + critical & high orders is covered": prioritized["covered"],
        f"S1 after ETA slip: only critical orders are covered (prediction {slipped['predicted_days']} d)":
            not critical_high["covered"] and critical["covered"],
        f"S2 is covered without action (prediction {contrast['predicted_days']} d)": s2["covered"],
    }
    return checks, similar


def read_rows(name: str) -> list[dict[str, str]]:
    with (SEED_DIR / "history" / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_env(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding what is already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


if __name__ == "__main__":
    main()
