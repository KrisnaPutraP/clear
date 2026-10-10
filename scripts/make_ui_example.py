"""Write docs/examples/case_s1.json: what the UI contract returns during S1.

Runs S1 with the scripted model on a temporary copy of the seed: the
exception, the planner's approval, then the ETA slip. The shapes are exactly
what the contract returns; the agent wording is illustrative. Regenerate
after a real Bedrock run for realistic text.

Usage: python scripts/make_ui_example.py
"""

import json
import tempfile
from pathlib import Path

from clear_agents.testing import ScriptedDirector
from clear_app.contract import Clear
from clear_tools.store import JsonStore, reset_runtime

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "docs" / "examples" / "case_s1.json"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = JsonStore(Path(tmp) / "runtime")
        reset_runtime(REPO_ROOT / "data" / "seed", store.root)
        clear = Clear(store, ScriptedDirector(store))
        events = clear.list_events()
        case_id = clear.send_event("S1-DOC-HOLD", wait=True)
        awaiting = clear.get_case(case_id)
        validation_id = awaiting["plan"]["actions"][0]["validation_id"]
        clear.submit_decision(case_id, validation_id, "Rina Hartono · Supply planner", "approved", wait=True)
        approved = clear.get_case(case_id)
        clear.send_event("S1-ETA-SLIP", wait=True)
        example = {
            "note": "Produced by a scripted run of S1 (scripts/make_ui_example.py). Shapes are exact; "
                    "agent wording is illustrative.",
            "list_events": events,
            "list_cases": clear.list_cases(),
            "get_case_awaiting_approval": awaiting,
            "get_case_after_approval": approved,
            "get_case_after_eta_slip": clear.get_case(case_id),
            "get_case_log": clear.get_case_log(case_id),
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(example, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {OUT.relative_to(REPO_ROOT).as_posix()}")


if __name__ == "__main__":
    main()
