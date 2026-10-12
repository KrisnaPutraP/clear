"""Shared fixtures: every test gets its own runtime copy of the committed seed."""

from pathlib import Path

import pytest

from clear_agents.testing import extract_fields
from clear_tools.store import JsonStore, reset_runtime

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"


@pytest.fixture(autouse=True)
def offline_backends(monkeypatch):
    """Tests use the deterministic baseline, the default model backend, and no real gateway unless a test
    opts in explicitly. The app test loads .env, which may set these for the rest of the session."""
    monkeypatch.delenv("CLEAR_PREDICTION_BACKEND", raising=False)
    monkeypatch.delenv("CLEAR_LLM_BACKEND", raising=False)
    for name in ("AGENTCORE_GATEWAY_TOOLS_URL", "CLEAR_ACTION_ROLE", "CLEAR_AGENTS_ROLE"):  # Never the real gateway.
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def store(tmp_path):
    runtime = tmp_path / "runtime"
    reset_runtime(SEED_DIR, runtime)
    return JsonStore(runtime)


@pytest.fixture
def extract():
    """Extract fields from get_documents() output the way a correct LLM extraction would."""
    return extract_fields
