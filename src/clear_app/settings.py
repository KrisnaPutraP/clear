"""Local settings: where the data lives and how .env is loaded."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_DIR = REPO_ROOT / "data" / "seed"


def runtime_dir() -> Path:
    """Runtime data directory; CLEAR_RUNTIME_DIR overrides the default data/runtime."""
    return Path(os.environ.get("CLEAR_RUNTIME_DIR", REPO_ROOT / "data" / "runtime"))


def load_env(path: Path = REPO_ROOT / ".env") -> None:
    """Load KEY=VALUE lines into os.environ. Values already set win; empty values are skipped."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            if value.strip():
                os.environ.setdefault(key.strip(), value.strip())
