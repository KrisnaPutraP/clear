"""Build the shared CLEAR service for HTTP clients using the demo's backend selection."""

import os

from clear_agents import runner
from clear_agents.testing import ScriptedDirector
from clear_app import settings
from clear_app.contract import Clear, LocalAgents
from clear_tools.store import JsonStore, reset_runtime


def create_clear() -> Clear:
    settings.load_env()
    if os.environ.get("CLEAR_UI_SCRIPTED") == "1":
        # Scripted development must never require SAP prediction credentials.
        os.environ["CLEAR_PREDICTION_BACKEND"] = "baseline"
    else:
        from clear_aws import settings as aws_settings
        from clear_aws.dynamo_store import DynamoStore
        from clear_aws.remote import GatewayAgents, RuntimeAgents

        if os.environ.get(aws_settings.RUNTIME_ARN_SETTING):
            store = DynamoStore.from_env()
            return Clear(store, agents=RuntimeAgents.from_env(store))
        if os.environ.get(aws_settings.GATEWAY_URL_SETTING):
            store = DynamoStore.from_env()
            return Clear(store, agents=GatewayAgents(store))

    runtime = settings.runtime_dir()
    if not runtime.exists():
        reset_runtime(settings.SEED_DIR, runtime)
    store = JsonStore(runtime)
    model = ScriptedDirector(store) if os.environ.get("CLEAR_UI_SCRIPTED") == "1" else runner.live_model
    return Clear(store, model)


def service_info(clear: Clear) -> dict:
    """Display configuration without returning credentials or claiming live connectivity."""
    local = isinstance(clear.agents, LocalAgents)
    scripted = local and isinstance(clear.agents.model_for, ScriptedDirector)
    mode = "scripted" if scripted else "local" if local else type(clear.agents).__name__
    return {
        "status": "ok",
        "running": clear.running,
        "mode": mode,
        "model": "Scripted model (development only)" if scripted else runner.live_model_name(),
        "prediction": "SAP-RPT-1.6 with baseline fallback"
        if not scripted and os.environ.get("CLEAR_PREDICTION_BACKEND", "").lower() == "auto"
        else "Baseline median",
        "synthetic_data": True,
    }
