"""Shared fixtures: every test gets its own runtime copy of the committed seed."""

from pathlib import Path

import pytest

from clear_agents.testing import extract_fields
from clear_tools.store import JsonStore, reset_runtime

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"


@pytest.fixture(autouse=True)
def offline_predictions(monkeypatch):
    """Tests use the deterministic baseline unless a test opts into SAP-RPT explicitly."""
    monkeypatch.delenv("CLEAR_PREDICTION_BACKEND", raising=False)


@pytest.fixture
def store(tmp_path):
    runtime = tmp_path / "runtime"
    reset_runtime(SEED_DIR, runtime)
    return JsonStore(runtime)


@pytest.fixture
def extract():
    """Extract fields from get_documents() output the way a correct LLM extraction would."""
    return extract_fields
