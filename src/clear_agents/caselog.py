"""Cases and the case log (docs/PLAN.md §6c, §7c, §7d).

One case per shipment exception. The case log is one append-only list of
entries in the data store, written by Strands hooks on every agent. It feeds
the UI timeline, serves as the audit trail, and together with the case
status lets a run pause for approval and resume.

Each tool step is logged with a one-line summary computed by code from the
tool result, plus the source of its numbers. Agents' short written reasons
are logged as notes; model reasoning is not.
"""

import json

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry, MessageAddedEvent

from clear_agents.plan import RecoveryPlan
from clear_tools import records
from clear_tools.store import JsonStore

CASES = "records/cases"
LOG = "records/case_log"
SPECIALISTS = {"evidence_agent": "Evidence", "impact_agent": "Impact & Options", "action_agent": "Action"}
NOTE_LIMIT = 400


def open_case(store: JsonStore, shipment_id: str) -> dict:
    """The shipment's open case, or a new one."""
    for case in store.read(CASES):
        if case["shipment_id"] == shipment_id and case["status"] != "closed":
            return case
    return records.add(store, "case", {"shipment_id": shipment_id, "status": "analyzing",
                                       "status_reason": None, "plan": None})


def get_case(store: JsonStore, case_id: str) -> dict:
    return records.get(store, "case", case_id)


def update_case(store: JsonStore, case_id: str, **fields) -> dict:
    cases = store.read(CASES)
    case = next(c for c in cases if c["case_id"] == case_id)
    case.update(fields, updated_at=records.now())
    store.write(CASES, cases)
    return case


def log(store: JsonStore, case_id: str, actor: str, kind: str, summary: str, **extra) -> dict:
    """Append one entry. kind: event, delegation, tool, note, approval, decision, status, error."""
    entries = store.read(LOG)
    entry = {"seq": len(entries) + 1, "case_id": case_id, "at": records.now(), "actor": actor,
             "kind": kind, "summary": summary, **{k: v for k, v in extra.items() if v is not None}}
    entries.append(entry)
    store.write(LOG, entries)
    return entry


def read_log(store: JsonStore, case_id: str, after_seq: int = 0) -> list[dict]:
    return [e for e in store.read(LOG) if e["case_id"] == case_id and e["seq"] > after_seq]


class CaseLogHooks(HookProvider):
    """Writes one agent's delegations, tool steps, and notes to the case log."""

    def __init__(self, store: JsonStore, case_id: str, actor: str):
        self.store, self.case_id, self.actor = store, case_id, actor

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self._before_tool)
        registry.add_callback(AfterToolCallEvent, self._after_tool)
        registry.add_callback(MessageAddedEvent, self._message_added)

    def _before_tool(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        if name in SPECIALISTS:
            instruction = str((event.tool_use.get("input") or {}).get("input", ""))
            log(self.store, self.case_id, self.actor, "delegation",
                f"Asked {SPECIALISTS[name]}: {_shorten(instruction)}", tool=name)

    def _after_tool(self, event: AfterToolCallEvent) -> None:
        name = event.tool_use["name"]
        if name in SPECIALISTS or name == RecoveryPlan.__name__:  # Specialists log their own steps.
            return
        text = " ".join(block.get("text", "") for block in event.result.get("content", []))
        if event.result.get("status") == "error":
            log(self.store, self.case_id, self.actor, "tool", _shorten(text), tool=name, flag="error")
            return
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = None
        summary, source, flag = summarize(name, result) if isinstance(result, dict) else (_shorten(text), None, None)
        log(self.store, self.case_id, self.actor, "tool", summary, tool=name, source=source, flag=flag)

    def _message_added(self, event: MessageAddedEvent) -> None:
        message = event.message
        if message.get("role") != "assistant":
            return
        text = " ".join(block["text"] for block in message.get("content", []) if "text" in block).strip()
        if text:
            log(self.store, self.case_id, self.actor, "note", _shorten(text, NOTE_LIMIT))


Summary = tuple[str, str | None, str | None]  # (one-line summary, source of the numbers, flag)

S4 = "S/4HANA (mock)"
RULES = "business rules"


def summarize(tool: str, result: dict) -> Summary:
    """One-line summary, source of the numbers, and flag for a tool result."""
    summarizer = _SUMMARIZERS.get(tool)
    return summarizer(result) if summarizer else (tool, None, None)


def _shipment(r: dict) -> Summary:
    exception = r.get("exception")
    tail = f"; {exception['exception_type']} ({exception['congestion_level']} congestion)" if exception else ""
    return f"{r['shipment_id']}: {r['status']}, ETA {r['eta']}{tail}", "logistics event feed (simulated)", None


def _purchase_order(r: dict) -> Summary:
    header, item = r["A_PurchaseOrder"], r["A_PurchaseOrderItem"][0]
    supplier = f" from {r['A_Supplier']['SupplierName']}" if r.get("A_Supplier") else ""
    return (f"PO {header['PurchaseOrder']}: {item['OrderQuantity']:g} {item['PurchaseOrderQuantityUnit']} "
            f"{item['Material']} for plant {item['Plant']}{supplier}", S4, None)


def _documents(r: dict) -> Summary:
    return f"{len(r['documents'])} of {len(r['required_documents'])} required documents", "shipping documents", None


def _inventory(r: dict) -> Summary:
    def plant(p: dict) -> str:
        in_transit = f", {p['in_transit_t']:g} in transit" if p["in_transit_t"] else ""
        return f"{p['plant']} {p['unrestricted_t']:g} t (safety {p['safety_stock_t']:g}{in_transit})"

    return f"{r['material']}: " + "; ".join(plant(p) for p in r["plants"]), S4, None


def _reconcile(r: dict) -> Summary:
    if r["consistent"]:
        return f"{r['reconciliation_id']}: documents agree with each other and with the purchase order", \
            "deterministic check", None
    findings = [f"{d['field']} differs in {', '.join(d['mismatched_documents'])}" for d in r["discrepancies"]]
    if r["missing_documents"]:
        findings.append("missing " + ", ".join(r["missing_documents"]))
    if r["not_extracted"] or r["unverified_extractions"]:
        findings.append(f"{len(r['not_extracted'])} fields not extracted, "
                        f"{len(r['unverified_extractions'])} extractions unverified")
    return (f"{r['reconciliation_id']}: " + "; ".join(findings), "deterministic check",
            "discrepancy" if r["discrepancies"] else None)


def _prediction(r: dict) -> Summary:
    basis = r["basis"]
    if basis.get("interval_days"):
        low, high = basis["interval_days"]
        detail = f"likely {low:g}-{high:g}, from {basis['context_cases']} past exceptions"
    else:
        detail = f"median of {basis['cases']} similar past cases"
    if basis.get("fallback_reason"):
        detail += f"; SAP-RPT unavailable: {basis['fallback_reason']}"
    flag = "fallback" if basis.get("fallback_reason") else None
    return f"{r['prediction_id']}: {r['predicted_days']:g} days ({detail})", r["source"], flag


def _supply_risk(r: dict) -> Summary:
    transfer = r.get("transfer")
    plan = f"+{transfer['quantity_t']:g} t from {transfer['source_plant']}, " if transfer else ""
    verdict = "covered" if r["covered"] else f"short {r['shortage_t']:g} t"
    return (f"{r['assessment_id']} {plan}{r['priority_level']} orders: coverage {r['coverage_days']:g} "
            f"of {r['required_coverage_days']:g} days needed, {verdict}", "deterministic calculation", None)


def _validation(r: dict) -> Summary:
    if r["valid"]:
        return f"{r['validation_id']} valid: {r['quantity']:g} t from {r['source_plant']}", RULES, None
    reasons = " ".join(v["message"] for v in r["violations"])
    return f"{r['validation_id']} REJECTED: {reasons} Max feasible {r['max_feasible_quantity']:g} t.", RULES, "rejected"


def _sto(r: dict) -> Summary:
    return (f"STO {r['purchase_order']} created: {r['quantity_t']:g} t "
            f"{r['source_plant']} -> {r['destination_plant']}", S4, "write")


_SUMMARIZERS = {
    "get_shipment": _shipment,
    "get_purchase_order": _purchase_order,
    "get_documents": _documents,
    "get_inventory": _inventory,
    "reconcile_documents": _reconcile,
    "predict_resolution_time": _prediction,
    "calculate_supply_risk": _supply_risk,
    "validate_action": _validation,
    "create_stock_transport_order": _sto,
}


def _shorten(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
