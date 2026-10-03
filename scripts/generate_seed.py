"""Regenerate the committed seed data in data/seed/ (docs/PLAN.md §4).

Runs the generators in clear_datagen with fixed random seeds, so the output is
reproducible, then resets data/runtime/ from the new seed.

Usage: python scripts/generate_seed.py
"""

import shutil
from pathlib import Path

from clear_datagen import generate_seed
from clear_tools.store import reset_runtime

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = REPO_ROOT / "data" / "seed"
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"


def main() -> None:
    # Generate next to the seed and swap, so a failing generator leaves the old seed intact.
    staging = SEED_DIR.with_name("seed.new")
    if staging.exists():
        shutil.rmtree(staging)
    generate_seed(staging)
    if SEED_DIR.exists():
        shutil.rmtree(SEED_DIR)
    staging.rename(SEED_DIR)
    reset_runtime(SEED_DIR, RUNTIME_DIR)
    files = sum(1 for p in SEED_DIR.rglob("*") if p.is_file())
    print(f"Generated {files} files in data/seed and reset data/runtime")


if __name__ == "__main__":
    main()
