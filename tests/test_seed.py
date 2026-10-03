"""The committed seed is exactly what the generators produce (docs/PLAN.md §4),
and the history table follows its documented shape and rules (§4d)."""

import csv
import statistics
from pathlib import Path

from clear_datagen import generate_seed, history

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"


def contents(root: Path) -> dict[str, str]:
    # Compare text with normalized line endings, so a Git checkout that
    # converts them does not count as a change.
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8").replace("\r\n", "\n")
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def read_history(name: str) -> list[dict]:
    with (SEED_DIR / "history" / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_committed_seed_matches_the_generators(tmp_path):
    generate_seed(tmp_path / "seed")

    assert contents(tmp_path / "seed") == contents(SEED_DIR), (
        "data/seed differs from the generators; run python scripts/generate_seed.py"
    )


def test_history_table_has_documented_shape():
    train, holdout = read_history("exception_history_train"), read_history("exception_history_holdout")

    assert len(train) + len(holdout) == history.ROWS
    assert len(holdout) == history.ROWS * history.HOLDOUT_SHARE
    assert list(train[0]) == history.COLUMNS


def test_document_exceptions_take_longer_than_congestion():
    rows = read_history("exception_history_train")

    def mean_days(exception_type):
        return statistics.mean(float(r["resolution_days"]) for r in rows if r["exception_type"] == exception_type)

    assert mean_days("document_discrepancy") > mean_days("port_congestion")
    assert mean_days("missing_document") > mean_days("port_congestion")
