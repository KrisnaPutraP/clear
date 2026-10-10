"""The Streamlit app, headless (streamlit.testing): S1 through the real buttons,
with the scripted model and a temporary runtime directory."""

import time
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from clear_tools.store import JsonStore

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


@pytest.fixture
def app(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("CLEAR_UI_SCRIPTED", "1")
    monkeypatch.setenv("CLEAR_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("CLEAR_PREDICTION_BACKEND", "baseline")  # .env must not switch tests to SAP-RPT.
    st.cache_resource.clear()
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.store = JsonStore(runtime)
    return app


def wait_for_status(app, status: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        cases = app.store.read("records/cases")
        if cases and cases[-1]["status"] == status:
            app.run()
            return
        time.sleep(0.2)
    raise AssertionError(f"case never reached {status}")


def test_app_starts_with_the_event_feed_and_the_scripted_banner(app):
    assert not app.exception
    labels = [button.label for button in app.button]
    assert {"S1 · Customs document hold", "S1 · ETA slip, berth congestion", "S2 · Yard congestion"} <= set(labels)
    assert any("not the real agent" in error.value for error in app.error)


def test_s1_from_the_event_button_to_the_approved_sto(app):
    app.button(key="event-S1-DOC-HOLD").click().run()
    wait_for_status(app, "awaiting_approval")

    assert not app.exception
    assert any("Rejected by validator" in error.value for error in app.error)

    app.button(key="approve").click().run()
    wait_for_status(app, "monitoring")

    assert not app.exception
    assert any("STO 4500001023 created" in success.value for success in app.success)
