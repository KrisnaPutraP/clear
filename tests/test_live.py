"""S1 and S2 on the real Bedrock model (docs/PLAN.md §1b). Opt-in, because each
run costs model usage: set CLEAR_LIVE_TESTS=1 with AWS credentials and
CLEAR_BEDROCK_MODEL_ID in the environment."""

import os

import pytest

from clear_app.contract import Clear

pytestmark = pytest.mark.skipif(
    os.environ.get("CLEAR_LIVE_TESTS") != "1" or not os.environ.get("CLEAR_BEDROCK_MODEL_ID"),
    reason="live Bedrock test; set CLEAR_LIVE_TESTS=1 and CLEAR_BEDROCK_MODEL_ID to run",
)


def test_s1_rejects_the_full_transfer_and_waits_for_approval(store):
    clear = Clear(store)
    case_id = clear.send_event("S1-DOC-HOLD", wait=True)
    case, log = clear.get_case(case_id), clear.get_case_log(case_id)

    assert case["status"] == "awaiting_approval", case["status_reason"]
    assert any(e.get("flag") == "discrepancy" for e in log)
    assert any(e.get("flag") == "rejected" for e in log)
    [action] = case["plan"]["actions"]
    assert action["validation"]["valid"]


def test_s2_keeps_the_plan(store):
    clear = Clear(store)
    case = clear.get_case(clear.send_event("S2-CONGESTION", wait=True))

    assert case["status"] == "monitoring", case["status_reason"]
    assert case["plan"]["actions"] == []
