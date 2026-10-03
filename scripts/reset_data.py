"""Reset demo state: replace data/runtime/ with a fresh copy of data/seed/.

Usage: python scripts/reset_data.py
"""

from pathlib import Path

from clear_tools.store import reset_runtime

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = REPO_ROOT / "data" / "seed"
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"


def main() -> None:
    reset_runtime(SEED_DIR, RUNTIME_DIR)
    seed, runtime = (p.relative_to(REPO_ROOT).as_posix() for p in (SEED_DIR, RUNTIME_DIR))
    print(f"Reset {runtime} from {seed}")


if __name__ == "__main__":
    main()
