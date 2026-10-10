"""UI contract (docs/PLAN.md §7b): the four operations a front end needs.

send_event, get_case, get_case_log, and submit_decision, plus list_events to
fill the event feed from the prepared catalog. Streamlit imports this
module; a custom front end can get the same operations over HTTP later
(docs/ui-contract.md). Agent runs happen in a background thread, so a UI can
poll get_case_log for a live timeline. One run at a time: the JSON store has
a single writer.
"""

import threading
from collections.abc import Callable

from clear_agents import caselog, runner
from clear_agents.plan import RecoveryPlan, render
from clear_tools import read
from clear_tools.events import CATALOG, prepared_event
from clear_tools.store import JsonStore


class Clear:
    def __init__(self, store: JsonStore, model_for: runner.ModelFactory = runner.bedrock_model):
        self.store = store
        self.model_for = model_for
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
        self._start(lambda: runner.work_event(self.store, case_id, event, self.model_for), wait)
        return case_id

    def get_case(self, case_id: str) -> dict:
        """Case status, shipment, and the current plan with every cited number filled in."""
        case = caselog.get_case(self.store, case_id)
        return {
            "case_id": case_id,
            "shipment_id": case["shipment_id"],
            "status": case["status"],
            "status_reason": case["status_reason"],
            "updated_at": case.get("updated_at", case["created_at"]),
            "running": self._busy.locked(),
            "shipment": read.get_shipment(self.store, case["shipment_id"]),
            "plan": render(self.store, RecoveryPlan.model_validate(case["plan"])) if case["plan"] else None,
        }

    def get_case_log(self, case_id: str, after_seq: int = 0) -> list[dict]:
        """Timeline entries of the case after the given sequence number."""
        return caselog.read_log(self.store, case_id, after_seq)

    def submit_decision(self, case_id: str, validation_id: str, approver: str, decision: str,
                        reason: str | None = None, wait: bool = False) -> dict:
        """Approve or reject a validated STO. An approval starts the run that executes it."""
        approval = self._prepare(lambda: runner.decide(self.store, case_id, validation_id, approver, decision, reason))
        if decision == "approved":
            self._start(lambda: runner.work_approval(self.store, case_id, approval, self.model_for), wait)
        else:
            self._busy.release()
        return approval

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
