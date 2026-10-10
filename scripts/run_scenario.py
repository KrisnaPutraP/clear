"""Run S1 or S2 end to end on Bedrock and print the case timeline.

Resets data/runtime first. Needs AWS credentials and CLEAR_BEDROCK_MODEL_ID
in the environment or in .env (see .env.example).

Usage:
    python scripts/run_scenario.py S1                        # stops at awaiting approval
    python scripts/run_scenario.py S1 --approve              # approves and executes the STO
    python scripts/run_scenario.py S1 --approve --eta-slip   # then fires the ETA slip
    python scripts/run_scenario.py S2
"""

import argparse

from clear_app import settings
from clear_app.contract import Clear
from clear_tools.store import JsonStore, reset_runtime

FIRST_EVENT = {"S1": "S1-DOC-HOLD", "S2": "S2-CONGESTION"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario", choices=sorted(FIRST_EVENT))
    parser.add_argument("--approve", action="store_true", help="approve the validated STO as 'Demo Planner'")
    parser.add_argument("--eta-slip", action="store_true", help="S1 only: fire the ETA slip after the approval")
    args = parser.parse_args()

    settings.load_env()
    store = JsonStore(settings.runtime_dir())
    reset_runtime(settings.SEED_DIR, store.root)
    clear = Clear(store)
    case_id = clear.send_event(FIRST_EVENT[args.scenario], wait=True)
    shown = show(clear, case_id, 0)

    case = clear.get_case(case_id)
    if args.approve and case["status"] == "awaiting_approval":
        validation_id = case["plan"]["actions"][0]["validation_id"]
        clear.submit_decision(case_id, validation_id, "Demo Planner", "approved", wait=True)
        shown = show(clear, case_id, shown)
    if args.scenario == "S1" and args.eta_slip:
        clear.send_event("S1-ETA-SLIP", wait=True)
        show(clear, case_id, shown)
    print(f"\n{case_id}: {clear.get_case(case_id)['status']}")


def show(clear: Clear, case_id: str, after_seq: int) -> int:
    for entry in clear.get_case_log(case_id, after_seq):
        flag = f" [{entry['flag']}]" if entry.get("flag") else ""
        source = f"  <{entry['source']}>" if entry.get("source") else ""
        print(f"{entry['seq']:>3} {entry['actor']:<17} {entry['summary']}{flag}{source}")
        after_seq = entry["seq"]
    return after_seq


if __name__ == "__main__":
    main()
