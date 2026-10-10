"""Running variants through the agents and scoring them (docs/PLAN.md §9c)."""

import time
from collections.abc import Callable
from pathlib import Path

from clear_app.contract import Clear
from clear_eval import oracle, scoring, variants
from clear_tools.store import JsonStore

# Store -> model factory, so a scripted factory can read the run's own store.
ModelFor = Callable[[JsonStore], Callable]


def run_variant(spec: dict, model_for: ModelFor, workdir: Path) -> dict:
    """Work one variant's event with the agents and score the plan against the oracle."""
    store = variants.build_store(spec, workdir / spec["id"])
    expected = oracle.expected(store, spec["event_id"])
    clear = Clear(store, model_for(store))
    started = time.monotonic()
    case_id = clear.send_event(spec["event_id"], wait=True)
    latency = time.monotonic() - started
    result = scoring.outcome(store, case_id)
    return {"variant": spec["id"], "family": spec["family"], "expected": expected, "outcome": result,
            "scores": scoring.score(expected, result), "latency_s": round(latency, 1)}


def run_batch(specs: list[dict], model_for: ModelFor, workdir: Path) -> dict:
    results = [run_variant(spec, model_for, workdir) for spec in specs]
    return {"summary": scoring.summarize(results), "results": results}
