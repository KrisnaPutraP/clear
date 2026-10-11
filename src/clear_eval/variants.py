"""Scenario variants for the reliability batch (docs/PLAN.md §9b).

Each variant is the committed seed with a few numbers changed: unrestricted
stock and safety stock per material and plant. Document-exception variants
use shipment SHP-1001 (its documents carry the planted discrepancy);
congestion variants use SHP-1002 (its documents agree). The decision each
variant needs is computed by clear_eval.oracle, not written here.
"""

from pathlib import Path

from clear_tools import s4
from clear_tools.store import JsonStore, reset_runtime

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"
BX, CX = "CHEM-BX40", "CHEM-CX20"
DOC_HOLD, CONGESTION = "S1-DOC-HOLD", "S2-CONGESTION"

# id, family, event, {(material, plant): unrestricted t}, {(material, plant): safety stock t}
_VARIANTS = [
    ("A1", "transfer and prioritize", DOC_HOLD, {}, {}),
    ("A2", "transfer and prioritize", DOC_HOLD, {(BX, "1100"): 34, (BX, "1200"): 64}, {}),
    ("A3", "transfer and prioritize", DOC_HOLD, {(BX, "1100"): 40, (BX, "1200"): 56}, {}),
    ("A4", "transfer and prioritize", DOC_HOLD, {(BX, "1100"): 30}, {}),
    ("B1", "transfer", DOC_HOLD, {(BX, "1200"): 100}, {}),
    ("B2", "transfer", DOC_HOLD, {(BX, "1100"): 44, (BX, "1200"): 80}, {}),
    ("B3", "transfer", DOC_HOLD, {(BX, "1100"): 36, (BX, "1200"): 90}, {(BX, "1200"): 50}),
    ("C1", "no feasible transfer", DOC_HOLD, {(BX, "1200"): 40}, {}),
    ("C2", "no feasible transfer", DOC_HOLD, {(BX, "1100"): 46, (BX, "1200"): 42}, {(BX, "1200"): 42}),
    ("C3", "no feasible transfer", DOC_HOLD, {(BX, "1100"): 54, (BX, "1200"): 30}, {}),
    ("C4", "no feasible transfer", DOC_HOLD, {(BX, "1100"): 48, (BX, "1200"): 40}, {}),
    ("D1", "no action", DOC_HOLD, {(BX, "1100"): 80}, {}),
    ("D2", "no action", DOC_HOLD, {(BX, "1100"): 72}, {}),
    ("D3", "no action", DOC_HOLD, {(BX, "1100"): 100}, {}),
    ("E1", "congestion, covered", CONGESTION, {}, {}),
    ("E2", "congestion, covered", CONGESTION, {(CX, "1100"): 200}, {}),
    ("E3", "congestion, covered", CONGESTION, {(CX, "1100"): 140}, {}),
    ("F1", "congestion, shortage", CONGESTION, {(CX, "1100"): 100}, {}),
    ("F2", "congestion, shortage", CONGESTION, {(CX, "1100"): 60}, {}),
    ("F3", "congestion, shortage", CONGESTION, {(CX, "1100"): 60, (CX, "1200"): 80}, {}),
]

VARIANTS = [
    {"id": vid, "family": family, "event_id": event_id, "stock": stock, "safety": safety}
    for vid, family, event_id, stock, safety in _VARIANTS
]


def variant(variant_id: str) -> dict:
    return next(v for v in VARIANTS if v["id"] == variant_id)


def build_store(spec: dict, runtime_dir: Path) -> JsonStore:
    """A fresh runtime copy of the seed with the variant's numbers applied."""
    reset_runtime(SEED_DIR, runtime_dir)
    store = JsonStore(runtime_dir)
    stock = store.read(s4.STOCK)
    for row in stock:
        key = (row["Material"], row["Plant"])
        if key in spec["stock"] and row["InventoryStockType"] == s4.UNRESTRICTED:
            row["MatlWrhsStkQtyInMatlBaseUnit"] = spec["stock"][key]
    store.write(s4.STOCK, stock)
    planning = store.read(s4.SUPPLY_PLANNING)
    for row in planning:
        key = (row["Product"], row["Plant"])
        if key in spec["safety"]:
            row["SafetyStockQuantity"] = spec["safety"][key]
    store.write(s4.SUPPLY_PLANNING, planning)
    return store
