"""Data access layer (docs/PLAN.md §4c).

Local development reads and writes JSON files under data/runtime/. The
DynamoDB backend for deployment lives outside this package, so tool logic
stays free of AWS dependencies.

data/seed/ holds the committed starting state. reset_runtime() replaces the
runtime directory with an exact copy of it, so every demo run and every test
starts from the same state.
"""

import shutil
from pathlib import Path


def reset_runtime(seed_dir: Path, runtime_dir: Path) -> None:
    """Replace runtime_dir with an exact copy of seed_dir."""
    seed_dir, runtime_dir = seed_dir.resolve(), runtime_dir.resolve()
    if not seed_dir.is_dir():
        raise FileNotFoundError(f"Seed directory not found: {seed_dir}")
    # runtime_dir is deleted below, so it must not be, contain, or sit inside the seed.
    overlap = (
        runtime_dir == seed_dir
        or runtime_dir in seed_dir.parents
        or seed_dir in runtime_dir.parents
    )
    if overlap:
        raise ValueError(f"Seed and runtime directories overlap: {seed_dir}, {runtime_dir}")
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    shutil.copytree(seed_dir, runtime_dir)
