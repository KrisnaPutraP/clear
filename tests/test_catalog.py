"""One dispatch table for the nine tools (docs/PLAN.md §5a, §5b): the agents' tools and the
Lambda function behind the gateway name the same tools with the same arguments."""

import inspect

import pytest

from clear_agents import tools
from clear_tools import catalog


def agent_tool_specs() -> dict[str, dict]:
    def unused(name, arguments):
        raise AssertionError(name)

    agent_tools = tools.evidence_tools(unused) + tools.impact_tools(unused) + tools.action_tools(unused)
    return {tool.tool_spec["name"]: tool.tool_spec for tool in agent_tools}


def test_agents_and_catalog_name_the_same_tools_and_arguments():
    specs = agent_tool_specs()

    assert set(specs) == set(catalog.TOOLS)
    for name, spec in specs.items():
        parameters = list(inspect.signature(catalog.TOOLS[name]).parameters)[1:]  # After the store.
        assert sorted(spec["inputSchema"]["json"]["properties"]) == sorted(parameters), name


def test_local_tools_run_through_the_catalog(store):
    invoke = tools.local(store)

    assert invoke("get_shipment", {"shipment_id": "SHP-1001"})["purchase_order"] == "4500001021"


def test_unknown_tools_and_bad_arguments_are_refused(store):
    with pytest.raises(LookupError):
        catalog.call(store, "drop_tables", {})
    with pytest.raises(ValueError, match="get_shipment"):
        catalog.call(store, "get_shipment", {})
    with pytest.raises(ValueError):
        catalog.call(store, "get_shipment", {"shipment_id": "SHP-1001", "quantity_t": 5})
