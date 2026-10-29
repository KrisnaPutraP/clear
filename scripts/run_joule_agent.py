"""Serve CLEAR as an A2A agent for SAP Joule.

Does not reset any data: it works on the same data as the UI. With
AGENTCORE_GATEWAY_TOOLS_URL set (as for the UI), the tools run behind the
gateway on the DynamoDB table; otherwise in this process on data/runtime.
Settings in .env: CLEAR_A2A_URL, the public URL Joule reaches this server at
(it goes into the agent card); CLEAR_A2A_USER and CLEAR_A2A_PASSWORD, the
Basic credentials of the BTP destination.

Usage:
    python scripts/run_joule_agent.py              # port 10000
    python scripts/run_joule_agent.py --port 8080
    python scripts/run_joule_agent.py --scripted   # scripted model, for trying the conversation only

On Cloud Foundry (manifest.yml) it listens on all interfaces at the port in PORT.
"""

import argparse
import os

import uvicorn

from clear_agents import runner
from clear_agents.testing import ScriptedDirector
from clear_app import joule, settings
from clear_app.contract import Clear
from clear_aws import settings as aws_settings
from clear_tools.store import JsonStore, reset_runtime


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 10000)))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--scripted", action="store_true", help="drive the agents with the scripted model")
    args = parser.parse_args()

    settings.load_env()
    if args.scripted:
        os.environ["CLEAR_PREDICTION_BACKEND"] = "baseline"
    if not args.scripted and os.environ.get(aws_settings.GATEWAY_URL_SETTING):
        from clear_aws.dynamo_store import DynamoStore
        from clear_aws.remote import GatewayAgents

        store = DynamoStore.from_env()
        clear = Clear(store, agents=GatewayAgents(store))
        print("Tools: AgentCore Gateway, data: DynamoDB")
    else:
        runtime = settings.runtime_dir()
        if not runtime.exists():
            reset_runtime(settings.SEED_DIR, runtime)
        store = JsonStore(runtime)
        clear = Clear(store, ScriptedDirector(store) if args.scripted else runner.live_model)
        print(f"Tools: this process, data: {runtime}")
    print("Agents: scripted model" if args.scripted else f"Agents: {runner.live_model_name()}")

    url = os.environ.get("CLEAR_A2A_URL") or f"http://localhost:{args.port}/"
    password = os.environ.get("CLEAR_A2A_PASSWORD")
    if not password:
        print("No CLEAR_A2A_PASSWORD: the server accepts every request. Do not expose it publicly.")
    print(f"Agent card: {url.rstrip('/')}/.well-known/agent-card.json")
    app = joule.build_app(clear, url, os.environ.get("CLEAR_A2A_USER"), password)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
