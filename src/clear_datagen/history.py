"""Exception history table for predict_resolution_time (docs/PLAN.md §4d).

1,000 rows x 10 columns: exception attributes plus the target
resolution_days, generated from the explicit rules below with noise. 20% of
the rows are held out for the quality check in §3c. The relationships are
designed to be plausible (document exceptions take longer than congestion,
congestion adds days); they are not real statistics. data/README.md lists
the same rules in prose.
"""

import random

SEED = 20261031
ROWS = 1_000
HOLDOUT_SHARE = 0.2

COLUMNS = [
    "exception_type", "port", "cargo_category", "missing_documents", "has_document_discrepancy",
    "congestion_level", "forwarder", "origin_country", "month", "resolution_days",
]

EXCEPTION_TYPES = {"document_discrepancy": 0.35, "missing_document": 0.20,
                   "port_congestion": 0.30, "customs_inspection": 0.15}
PORTS = {"Tanjung Priok": 0.55, "Tanjung Perak": 0.30, "Belawan": 0.15}
CARGO = {"bleaching_chemical": 0.30, "caustic": 0.30, "sizing_agent": 0.20, "retention_aid": 0.20}
FORWARDERS = ["FWD-A", "FWD-B", "FWD-C", "FWD-D", "FWD-E"]
ORIGINS = ["CN", "DE", "FI", "JP", "KR", "US"]
PEAK_MONTHS = {10, 11, 12}

# Congestion level probabilities: port_congestion exceptions only occur when
# the port is congested; peak season shifts every exception toward congestion.
CONGESTION = {
    ("port_congestion", False): {"elevated": 0.40, "high": 0.60},
    ("port_congestion", True): {"elevated": 0.30, "high": 0.70},
    ("other", False): {"normal": 0.60, "elevated": 0.25, "high": 0.15},
    ("other", True): {"normal": 0.45, "elevated": 0.30, "high": 0.25},
}

# Additive effects on resolution days.
BASE_DAYS = {"document_discrepancy": 2.5, "missing_document": 3.0,
             "port_congestion": 0.6, "customs_inspection": 1.8}
PORT_DAYS = {"Tanjung Priok": 0.3, "Tanjung Perak": 0.0, "Belawan": -0.2}
CONGESTION_DAYS = {"normal": 0.0, "elevated": 0.5, "high": 1.0}
CARGO_DAYS = {"bleaching_chemical": 0.3, "caustic": 0.2, "sizing_agent": 0.0, "retention_aid": 0.0}
FORWARDER_DAYS = {"FWD-A": -0.2, "FWD-C": 0.4}
EXTRA_MISSING_DOCUMENT_DAYS = 0.8  # each missing document after the first
DISCREPANCY_DAYS = 0.6  # discrepancy found on an exception of another type
NOISE_SD = 0.35
MIN_DAYS = 0.5


def generate(seed: int = SEED, rows: int = ROWS) -> list[dict]:
    rng = random.Random(seed)
    return [_row(rng) for _ in range(rows)]


def split(rows: list[dict], seed: int = SEED) -> tuple[list[dict], list[dict]]:
    """(train, holdout), holding out HOLDOUT_SHARE of the rows at random."""
    order = list(range(len(rows)))
    random.Random(seed + 1).shuffle(order)
    held_out = set(order[: round(len(rows) * HOLDOUT_SHARE)])
    train = [row for i, row in enumerate(rows) if i not in held_out]
    holdout = [row for i, row in enumerate(rows) if i in held_out]
    return train, holdout


def _row(rng: random.Random) -> dict:
    exception_type = _pick(rng, EXCEPTION_TYPES)
    port = _pick(rng, PORTS)
    cargo = _pick(rng, CARGO)
    forwarder = rng.choice(FORWARDERS)
    origin = rng.choice(ORIGINS)  # No effect: a distractor column.
    month = rng.randint(1, 12)
    kind = "port_congestion" if exception_type == "port_congestion" else "other"
    congestion = _pick(rng, CONGESTION[(kind, month in PEAK_MONTHS)])

    missing = 0
    if exception_type == "missing_document":
        missing = 1 if rng.random() < 0.75 else 2
    discrepancy = exception_type == "document_discrepancy" or (
        exception_type == "missing_document" and rng.random() < 0.15
    )

    days = (
        BASE_DAYS[exception_type]
        + PORT_DAYS[port]
        + CONGESTION_DAYS[congestion]
        + CARGO_DAYS[cargo]
        + FORWARDER_DAYS.get(forwarder, 0.0)
        + EXTRA_MISSING_DOCUMENT_DAYS * max(0, missing - 1)
        + (DISCREPANCY_DAYS if discrepancy and exception_type != "document_discrepancy" else 0.0)
        + rng.gauss(0.0, NOISE_SD)
    )
    return {
        "exception_type": exception_type,
        "port": port,
        "cargo_category": cargo,
        "missing_documents": missing,
        "has_document_discrepancy": "true" if discrepancy else "false",
        "congestion_level": congestion,
        "forwarder": forwarder,
        "origin_country": origin,
        "month": month,
        "resolution_days": round(max(MIN_DAYS, days), 1),
    }


def _pick(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]
