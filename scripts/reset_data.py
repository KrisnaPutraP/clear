"""Reset demo state to a fresh copy of data/seed/.

Usage:
    python scripts/reset_data.py          # data/runtime/
    python scripts/reset_data.py --aws    # the deployment's DynamoDB table (docs/deployment.md)
"""

import argparse
from pathlib import Path

from clear_tools.store import reset_runtime

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = REPO_ROOT / "data" / "seed"
RUNTIME_DIR = REPO_ROOT / "data" / "runtime"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aws", action="store_true", help="reset the DynamoDB table instead of data/runtime/")
    args = parser.parse_args()

    if args.aws:
        from clear_app import settings
        from clear_aws.dynamo_store import DynamoStore, reset_table

        settings.load_env()
        store = DynamoStore.from_env()
        reset_table(SEED_DIR, store)
        print(f"Reset DynamoDB table {store.table} from data/seed")
        return
    reset_runtime(SEED_DIR, RUNTIME_DIR)
    seed, runtime = (p.relative_to(REPO_ROOT).as_posix() for p in (SEED_DIR, RUNTIME_DIR))
    print(f"Reset {runtime} from {seed}")


if __name__ == "__main__":
    main()
