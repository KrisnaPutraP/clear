"""UI contract (docs/PLAN.md §7b): the four operations a front end needs.

send_event, get_case, get_case_log, and submit_decision, plus list_events and
list_cases to fill the event feed and a case picker. Streamlit imports this
module; a custom front end can get the same operations over HTTP later
(docs/ui-contract.md). Agent runs happen in a background thread, so a UI can
poll get_case_log for a live timeline. One run at a time: the data store has
a single writer.

Agents run in this process by default (LocalAgents). Deployed, they run on
AgentCore Runtime instead (clear_aws.remote.RuntimeAgents) and the store is
DynamoDB; the operations stay the same.
"""

import contextlib
import threading
from collections.abc import Callable
from typing import Protocol

from clear_agents import caselog, runner
from clear_agents.plan import RecoveryPlan, render
from clear_tools import read
from clear_tools.events import CATALOG, prepared_event
from clear_tools.store import JsonStore


class Agents(Protocol):
    """Where agent runs happen. Both methods block until the run ends and return the case."""

    def work_event(self, case_id: str, event: dict) -> dict: ...

    def work_approval(self, case_id: str, approval: dict) -> dict: ...


class LocalAgents:
    """Agents in this process, with tools bound to the store."""

    def __init__(self, store: JsonStore, model_for: runner.ModelFactory):
        self.store, self.model_for = store, model_for

    def work_event(self, case_id: str, event: dict) -> dict:
        return runner.work_event(self.store, case_id, event, self.model_for)

    def work_approval(self, case_id: str, approval: dict) -> dict:
        return runner.work_approval(self.store, case_id, approval, self.model_for)


class Clear:
    def __init__(self, store: JsonStore, model_for: runner.ModelFactory = runner.live_model,
                 agents: Agents | None = None):
        self.store = store
        self.agents = agents or LocalAgents(store, model_for)
        self._busy = threading.Lock()
        self._thread: threading.Thread | None = None

    def list_events(self) -> list[dict]:
        """Prepared events for the event feed."""
        keys = ("event_id", "scenario", "type", "shipment_id", "description")
        return [{k: event[k] for k in keys} for event in self.store.read(CATALOG)]

    def send_event(self, event_id: str, wait: bool = False) -> str:
        """Record a logistics event and start the agents on its case. Returns the case_id."""
        event = prepared_event(self.store, event_id)
        case_id = self._prepare(lambda: runner.open_case_for_event(self.store, event))
        self._start(lambda: self.agents.work_event(case_id, event), wait)
        return case_id

    @property
    def running(self) -> bool:
        """Whether an agent run is in progress."""
        return self._busy.locked()

    def list_cases(self) -> list[dict]:
        """All cases, newest first, for a case picker."""
        keys = ("case_id", "shipment_id", "status")
        return [{k: case[k] for k in keys} for case in reversed(self.store.read(caselog.CASES))]

    def get_case(self, case_id: str) -> dict:
        """Case status, shipment, documents, stock, and the plan with every cited number filled in."""
        case = caselog.get_case(self.store, case_id)
        shipment = read.get_shipment(self.store, case["shipment_id"])
        material = read.get_purchase_order(self.store, shipment["purchase_order"])["A_PurchaseOrderItem"][0]["Material"]
        reconciliations = [r for r in self.store.read("records/reconciliations")
                           if r["shipment_id"] == case["shipment_id"]]
        return {
            "case_id": case_id,
            "shipment_id": case["shipment_id"],
            "status": case["status"],
            "status_reason": case["status_reason"],
            "updated_at": case.get("updated_at", case["created_at"]),
            "running": self.running,
            "shipment": shipment,
            "documents": read.get_documents(self.store, case["shipment_id"]),
            "reconciliation": reconciliations[-1] if reconciliations else None,
            "inventory": read.get_inventory(self.store, material),
            "plan": render(self.store, RecoveryPlan.model_validate(case["plan"])) if case["plan"] else None,
        }

    def get_case_log(self, case_id: str, after_seq: int = 0) -> list[dict]:
        """Timeline entries of the case after the given sequence number."""
        return caselog.read_log(self.store, case_id, after_seq)

    def submit_decision(self, case_id: str, validation_id: str, approver: str, decision: str,
                        reason: str | None = None, wait: bool = False) -> dict:
        """Approve or reject a validated STO. An approval starts the run that executes it."""
        def decide():
            # Bind a web client's decision to the current case and pending plan.
            # Do this inside the same lock as the write, so two requests cannot
            # both approve a stale plan or approve another case's validation.
            case = caselog.get_case(self.store, case_id)
            pending = (case.get("plan") or {}).get("actions", [])
            if case["status"] != "awaiting_approval" or not any(
                action["validation_id"] == validation_id and action["status"] == "awaiting_approval"
                for action in pending
            ):
                raise PermissionError("This validation is not awaiting approval on the current case plan.")
            return runner.decide(self.store, case_id, validation_id, approver, decision, reason)

        approval = self._prepare(decide)
        if decision == "approved":
            self._start(lambda: self.agents.work_approval(case_id, approval), wait)
        else:
            self._busy.release()
        return approval

    def snapshot(self):
        """Context in which reads see one state of the store: a single round trip on DynamoDB."""
        snapshot = getattr(self.store, "snapshot", None)
        return snapshot() if snapshot else contextlib.nullcontext()

    def wait(self, timeout: float | None = None) -> None:
        """Block until the current run finishes."""
        if self._thread:
            self._thread.join(timeout)

    def _prepare(self, step: Callable):
        if not self._busy.acquire(blocking=False):
            raise RuntimeError("An agent run is in progress; wait for it to finish.")
        try:
            return step()
        except BaseException:
            self._busy.release()
            raise

    def _start(self, work: Callable, wait: bool) -> None:
        def target() -> None:
            try:
                work()
            finally:
                self._busy.release()

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        if wait:
            self._thread.join()
