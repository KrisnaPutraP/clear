"""What the AgentCore Runtime entrypoint does with an invocation (docs/PLAN.md §2c, §6c).

The UI records a logistics event or a human decision in the store itself,
then asks the runtime to work the case with one of two payloads:

    {"run": "event", "case_id": "CASE-0001", "event_id": "S1-DOC-HOLD"}
    {"run": "approval", "case_id": "CASE-0001", "approval_id": "APR-0001"}

The runtime reads the event or the approval from the store, runs the four
agents in this one process with their tools behind AgentCore Gateway, and
returns the case status. Details go to the case log in the store, as in a
local run, so a run that cannot finish still leaves a readable case.
"""

from clear_agents import caselog, runner
from clear_aws.dynamo_store import DynamoStore
from clear_aws.gateway import Gateway
from clear_tools import records
from clear_tools.events import prepared_event

RUNS = {"event": "event_id", "approval": "approval_id"}  # Run -> the ID it needs besides case_id.


def handle(payload: dict, store=None, model_for: runner.ModelFactory = runner.bedrock_model,
           gateway: Gateway | None = None) -> dict:
    run, case_id = _validated(payload)
    store = store or DynamoStore.from_env()
    caselog.get_case(store, case_id)  # An unknown case is the caller's error, not a failed run.
    try:
        with gateway or Gateway.from_env() as invoke_for:
            if run == "event":
                event = prepared_event(store, payload["event_id"])
                case = runner.work_event(store, case_id, event, model_for, invoke_for)
            else:
                approval = records.get(store, "approval", payload["approval_id"])
                case = runner.work_approval(store, case_id, approval, model_for, invoke_for)
    except Exception as error:  # For example, the gateway cannot be reached.
        case = runner.fail(store, case_id, f"{type(error).__name__}: {error}")
    return {"case_id": case_id, "status": case["status"], "status_reason": case["status_reason"]}


def _validated(payload: dict) -> tuple[str, str]:
    if not isinstance(payload, dict) or payload.get("run") not in RUNS:
        raise ValueError(f"The payload's run must be one of: {', '.join(RUNS)}")
    for field in ("case_id", RUNS[payload["run"]]):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ValueError(f"The payload needs {field}")
    return payload["run"], payload["case_id"]
