"""Display rules for the UI: contract output in, display-ready rows out.

No Streamlit here, so the rules are testable and reusable by any front end.
"""

from datetime import datetime

STATUS = {
    "analyzing": ("Analyzing", "blue"),
    "awaiting_approval": ("Awaiting approval", "orange"),
    "executing": ("Executing approved order", "blue"),
    "monitoring": ("Monitoring", "green"),
    "needs_human_decision": ("Needs a human decision", "red"),
}

# Timeline flags: label and how loudly to show them (§7c: validator rejections stand out).
FLAGS = {
    "rejected": ("Rejected by validator", "error"),
    "discrepancy": ("Document discrepancy", "warning"),
    "write": ("ERP write", "success"),
    "fallback": ("Prediction fallback", "warning"),
    "error": ("Error", "error"),
}

PRIORITY = {"all": "All orders", "critical_high": "Critical + high", "critical": "Critical only"}

DOCUMENT_TITLES = {
    "commercial_invoice": "Commercial invoice",
    "packing_list": "Packing list",
    "bill_of_lading": "Bill of lading",
    "certificate_of_analysis": "Certificate of analysis",
}


def timeline(entries: list[dict]) -> list[dict]:
    """Case log entries with a local time and flag styling."""
    rows = []
    for entry in entries:
        label, tone = FLAGS.get(entry.get("flag"), (None, None))
        rows.append({
            "time": datetime.fromisoformat(entry["at"]).astimezone().strftime("%H:%M:%S"),
            "actor": entry["actor"],
            "kind": entry["kind"],
            "summary": entry["summary"],
            "source": entry.get("source"),
            "flag": label,
            "tone": tone,
        })
    return rows


def option_rows(plan: dict) -> list[dict]:
    """The current plan, then every option, with the numbers the tools computed."""
    rows = [_option_row("Current plan", plan["impact"], recommended=False)]
    for option in plan["options"]:
        rows.append(_option_row(option["name"], option["assessment"],
                                recommended=option["name"] == plan["recommended_option"],
                                validation=option.get("validation")))
    return rows


def _option_row(name: str, assessment: dict, recommended: bool, validation: dict | None = None) -> dict:
    transfer = assessment["transfer"]
    covered = assessment["covered"]
    if validation is None:
        check = "—"
    else:
        check = f"{validation['validation_id']} " + ("valid" if validation["valid"] else "rejected")
    return {
        "option": name,
        "orders_served": PRIORITY[assessment["priority_level"]],
        "transfer": f"{transfer['quantity_t']:g} t from {transfer['source_plant']}" if transfer else "—",
        "coverage_days": assessment["coverage_days"],
        "needed_days": assessment["required_coverage_days"],
        "shortage_t": assessment["shortage_t"],
        "covered": covered,
        "label": "✓ covered" if covered else f"✕ short {assessment['shortage_t']:g} t",
        "deferred_orders": ", ".join(o["order_id"] for o in assessment["deferred_orders"]) or "—",
        "transfer_cost_usd": transfer["cost_usd"] if transfer else None,
        "validation": check,
        "recommended": recommended,
        "assessment_id": assessment["assessment_id"],
    }


def prediction_note(prediction: dict) -> str:
    """Where the predicted duration comes from, in one line."""
    basis = prediction["basis"]
    if basis.get("interval_days"):
        low, high = basis["interval_days"]
        note = f"SAP-RPT-1.6, likely {low:g}-{high:g} days, learned from {basis['context_cases']} past exceptions"
    else:
        note = f"Baseline: median of {basis['cases']} similar past exceptions"
    if basis.get("fallback_reason"):
        note += " (SAP-RPT unavailable, so the baseline was used)"
    return note


def similar_cases(prediction: dict) -> list[dict]:
    """Past exceptions SAP-RPT found most relevant, if the prediction came from it."""
    return [
        {"exception_type": c["exception_type"], "port": c["port"], "congestion": c["congestion_level"],
         "resolved_in_days": float(c["resolution_days"])}
        for c in prediction["basis"].get("similar_cases", [])
    ]


def document_lines(documents: list[dict], required: list[str], reconciliation: dict | None) -> list[dict]:
    """Each required document as lines, marking where a disagreeing value was read.

    "mismatch" marks the value that differs from the purchase order; "reference"
    marks the same field in documents that agree, for comparison.
    """
    mismatched, compared = set(), set()
    if reconciliation:
        for discrepancy in reconciliation["discrepancies"]:
            for extraction in reconciliation["verified_extractions"]:
                if extraction["field"] != discrepancy["field"]:
                    continue
                key = (extraction["document_type"], extraction["quote"])
                if extraction["document_type"] in discrepancy["mismatched_documents"]:
                    mismatched.add(key)
                else:
                    compared.add(key)
    texts = {d["document_type"]: d["text"] for d in documents}
    result = []
    for document_type in required:
        text = texts.get(document_type)
        lines = []
        for line in (text or "").splitlines():
            key = (document_type, line.strip())
            lines.append({"text": line, "mark": "mismatch" if key in mismatched
                          else "reference" if key in compared else None})
        result.append({"document_type": document_type, "title": DOCUMENT_TITLES.get(document_type, document_type),
                       "missing": text is None, "lines": lines})
    return result
