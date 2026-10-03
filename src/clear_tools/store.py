"""Data access layer (docs/PLAN.md §4c).

Local development reads and writes JSON, CSV, and text files under
data/runtime/. The DynamoDB backend for deployment lives outside this
package, so tool logic stays free of AWS dependencies.

data/seed/ holds the committed starting state. reset_runtime() replaces the
runtime directory with an exact copy of it, so every demo run and every test
starts from the same state.
"""

import csv
import json
import shutil
from pathlib import Path
from typing import Any


class JsonStore:
    """Files under one root directory, addressed by slash-separated names.

    JSON documents are named without their extension
    ("s4/API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod"); other files are named
    with it ("documents/SHP-1001/packing_list.txt").
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def read(self, name: str) -> Any:
        return json.loads(self.read_text(f"{name}.json"))

    def write(self, name: str, data: Any) -> None:
        path = self.root / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write then rename, so an interrupted run never leaves half a file.
        tmp = path.with_suffix(".json.tmp")
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        tmp.write_text(text, encoding="utf-8", newline="\n")
        tmp.replace(path)

    def read_text(self, name: str) -> str:
        return (self.root / name).read_text(encoding="utf-8")

    def read_csv(self, name: str) -> list[dict[str, str]]:
        with (self.root / name).open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def exists(self, name: str) -> bool:
        return (self.root / name).is_file()


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
