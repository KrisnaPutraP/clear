"""S1 and S2 on the real model (docs/PLAN.md §1b). Opt-in, because each run costs model usage: set
CLEAR_LIVE_TESTS=1. The model settings come from the environment or .env (see .env.example)."""

import os

import pytest

from clear_app import settings
from clear_app.contract import Clear

LIVE = os.environ.get("CLEAR_LIVE_TESTS") == "1"
if LIVE:
    settings.load_env()
BACKEND = os.environ.get("CLEAR_LLM_BACKEND", "bedrock").lower()  # conftest clears it per test; restored below.
CONFIGURED = bool(os.environ.get("SAP_LLM_DEPLOYMENT_ID" if BACKEND == "aicore" else "CLEAR_BEDROCK_MODEL_ID"))

pytestmark = pytest.mark.skipif(
    not (LIVE and CONFIGURED),
    reason="live model test; set CLEAR_LIVE_TESTS=1 and the model settings (see .env.example) to run",
)


@pytest.fixture(autouse=True)
def live_backend(monkeypatch):
    monkeypatch.setenv("CLEAR_LLM_BACKEND", BACKEND)


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
