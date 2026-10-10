"""CLEAR demo UI (docs/PLAN.md §7b): logistics event feed, agent timeline, and case panel.

Run: streamlit run app/streamlit_app.py
CLEAR_UI_SCRIPTED=1 drives the agents with the scripted model, for UI
development only; the page then says so in a banner.
"""

import html
import os

import altair as alt
import pandas as pd
import streamlit as st

from clear_agents import runner
from clear_agents.testing import ScriptedDirector
from clear_app import settings, view
from clear_app.contract import Clear
from clear_tools.store import JsonStore, reset_runtime

settings.load_env()
SCRIPTED = os.environ.get("CLEAR_UI_SCRIPTED") == "1"

EVENT_LABELS = {
    "S1-DOC-HOLD": "S1 · Customs document hold",
    "S1-ETA-SLIP": "S1 · ETA slip, berth congestion",
    "S2-CONGESTION": "S2 · Yard congestion",
}
PLANNERS = ["Rina Hartono · Supply planner", "Bayu Pratama · Plant logistics lead"]  # Fictional.
TONE = {"error": st.error, "warning": st.warning, "success": st.success}
BLUE = {"light": "#2a78d6", "dark": "#3987e5"}  # Emphasis: the recommended option.
MUTED = "#898781"  # Other options, the requirement rule.

st.set_page_config(page_title="CLEAR", page_icon="🧭", layout="wide")


@st.cache_resource
def get_clear() -> Clear:
    runtime = settings.runtime_dir()
    if not runtime.exists():
        reset_runtime(settings.SEED_DIR, runtime)
    store = JsonStore(runtime)
    return Clear(store, ScriptedDirector(store) if SCRIPTED else runner.bedrock_model)


clear = get_clear()


def main() -> None:
    sidebar()
    st.title("CLEAR")
    st.caption("Cross-border supply chain exception resolution. "
               "The LLM proposes, code computes and validates, a human approves.")
    if SCRIPTED:
        st.error("Scripted model: for UI development only. This is not the real agent.", icon="⚠️")

    event_feed()
    case_id = case_picker()
    if case_id:
        st.fragment(case_view, run_every="2s" if clear.running else None)(case_id)


def sidebar() -> None:
    with st.sidebar:
        st.subheader("Planner")
        st.session_state.planner = st.selectbox("Signed in as", PLANNERS)
        st.subheader("Engines")
        model = "Scripted model (development)" if SCRIPTED else \
            f"Amazon Bedrock · {os.environ.get('CLEAR_BEDROCK_MODEL_ID') or 'model not set'}"
        prediction = "SAP-RPT-1.6, baseline fallback" \
            if os.environ.get("CLEAR_PREDICTION_BACKEND", "").lower() == "auto" else "Baseline median"
        st.caption(f"Agents: {model}")
        st.caption(f"Resolution time: {prediction}")
        st.subheader("Demo data")
        st.caption("All data is synthetic and every name is fictional.")
        if st.button("Reset demo data", key="reset", disabled=clear.running, width="stretch"):
            reset_runtime(settings.SEED_DIR, settings.runtime_dir())
            get_clear.clear()
            st.session_state.pop("case_id", None)
            st.rerun()


def event_feed() -> None:
    st.subheader("Logistics event feed (simulated)")
    events = clear.list_events()
    for column, event in zip(st.columns(len(events)), events):
        label = EVENT_LABELS.get(event["event_id"], event["event_id"])
        if column.button(label, key=f"event-{event['event_id']}", help=event["description"],
                         disabled=clear.running, width="stretch"):
            st.session_state.case_id = clear.send_event(event["event_id"])
            st.session_state.was_running = True
            st.rerun()


def case_picker() -> str | None:
    cases = clear.list_cases()
    if not cases:
        st.info("Send an event to open a case.")
        return None
    ids = [c["case_id"] for c in cases]
    current = st.session_state.get("case_id")
    labels = {c["case_id"]: f"{c['case_id']} · {c['shipment_id']}" for c in cases}
    st.session_state.case_id = st.selectbox("Case", ids, index=ids.index(current) if current in ids else 0,
                                            format_func=labels.get)
    return st.session_state.case_id


def case_view(case_id: str) -> None:
    running = clear.running
    if st.session_state.get("was_running") and not running:
        st.session_state.was_running = False
        st.rerun()  # Full rerun: re-enable the event feed and stop polling.
    st.session_state.was_running = running

    case = clear.get_case(case_id)
    label, color = view.STATUS.get(case["status"], (case["status"], "gray"))
    st.markdown(f"**{case_id}** · shipment {case['shipment_id']} · :{color}-badge[{label}]"
                + (" · agents working…" if running else ""))
    if case["status_reason"]:
        st.caption(case["status_reason"])

    left, right = st.columns([2, 3], gap="large")
    with left:
        timeline(case_id)
    with right:
        tabs = ["Plan", "Approval", "Documents", "Stock"]
        default = "Approval" if case["status"] == "awaiting_approval" else "Plan"
        plan_tab, approval_tab, documents_tab, stock_tab = st.tabs(tabs, default=default)
        with plan_tab:
            plan_panel(case)
        with approval_tab:
            approval_panel(case)
        with documents_tab:
            documents_panel(case)
        with stock_tab:
            stock_panel(case)


def timeline(case_id: str) -> None:
    st.subheader("Agent timeline")
    with st.container(height=640):
        for row in view.timeline(clear.get_case_log(case_id)):
            text = f"`{row['time']}` **{row['actor']}** · {row['summary']}"
            if row["source"]:
                text += f"  \n:gray[source: {row['source']}]"
            if row["tone"]:
                TONE[row["tone"]](f"**{row['flag']}** · {text}")
            else:
                st.markdown(text)


def plan_panel(case: dict) -> None:
    plan = case["plan"]
    if not plan:
        st.info("The agents are working on this case…" if case["running"] else "No plan yet.")
        return
    impact, prediction = plan["impact"], plan["impact"]["prediction"]
    tiles = st.columns(3)
    tiles[0].metric("Predicted resolution", f"{prediction['predicted_days']:g} days",
                    help=view.prediction_note(prediction), border=True)
    tiles[1].metric("Coverage vs needed", f"{impact['coverage_days']:g} of {impact['required_coverage_days']:g} days",
                    help="Current plan: all orders served, no transfer.", border=True)
    tiles[2].metric("Shortage", f"{impact['shortage_t']:g} t", border=True)
    st.caption(f"Resolution time: {view.prediction_note(prediction)} · "
               "Stock: S/4HANA (mock) · Coverage and rules: deterministic code")

    rows = view.option_rows(plan)
    st.altair_chart(coverage_chart(rows), width="stretch")
    st.dataframe(pd.DataFrame(rows).drop(columns=["label", "recommended", "covered"]).rename(columns={
        "option": "Option", "orders_served": "Orders served", "transfer": "Transfer",
        "coverage_days": "Coverage (days)", "needed_days": "Needed (days)", "shortage_t": "Shortage (t)",
        "deferred_orders": "Deferred orders", "transfer_cost_usd": "Transfer cost (USD)",
        "validation": "Validation", "assessment_id": "Assessment",
    }), hide_index=True, width="stretch")

    st.markdown(f"**Recommendation.** {plan['recommendation']}")
    if plan["escalation"]:
        st.warning(f"**Needs a human decision:** {plan['escalation']}")
    st.caption(f"Next check: {plan['next_check']}")
    with st.expander("Evidence"):
        for item in plan["evidence"]:
            st.markdown(f"- {item['fact']} :gray[({item['source']})]")
    if similar := view.similar_cases(prediction):
        with st.expander("Past exceptions SAP-RPT found most similar"):
            st.dataframe(pd.DataFrame(similar), hide_index=True, width="stretch")


def coverage_chart(rows: list[dict]) -> alt.LayerChart:
    """Coverage per option against the requirement; position and labels carry covered or short."""
    theme = getattr(st.context.theme, "type", None) or "light"
    data = pd.DataFrame(rows)
    needed = float(data["needed_days"].max())
    top = max(needed, float(data["coverage_days"].max())) * 1.3
    data["label_x"] = data[["coverage_days", "needed_days"]].max(axis=1)  # Labels clear the requirement rule.
    base = alt.Chart(data).encode(y=alt.Y("option:N", sort=None, title=None, axis=alt.Axis(labelLimit=280)))
    bars = base.mark_bar(size=18, cornerRadiusEnd=4).encode(
        x=alt.X("coverage_days:Q", title="Days of coverage", scale=alt.Scale(domain=[0, top])),
        color=alt.condition(alt.datum.recommended, alt.value(BLUE.get(theme, BLUE["light"])), alt.value(MUTED)),
        tooltip=[alt.Tooltip("option:N", title="Option"), alt.Tooltip("coverage_days:Q", title="Coverage (days)"),
                 alt.Tooltip("needed_days:Q", title="Needed (days)"), alt.Tooltip("shortage_t:Q", title="Shortage (t)"),
                 alt.Tooltip("deferred_orders:N", title="Deferred orders")],
    )
    labels = base.mark_text(align="left", dx=8).encode(x="label_x:Q", text="label:N")
    requirement = alt.Chart(pd.DataFrame({"needed": [needed], "text": [f"needed {needed:g} days"]}))
    rule = requirement.mark_rule(color=MUTED, strokeWidth=2).encode(x="needed:Q")
    rule_label = requirement.mark_text(align="left", dx=4, dy=-6, baseline="bottom").encode(
        x="needed:Q", y=alt.value(0), text="text:N")
    return (bars + labels + rule + rule_label).properties(height=46 * len(rows) + 30)


def approval_panel(case: dict) -> None:
    plan = case["plan"]
    actions = plan["actions"] if plan else []
    pending = [a for a in actions if a["status"] == "awaiting_approval"]
    for action in (a for a in actions if a["status"] == "executed"):
        st.success(f"STO {action['purchase_order']} created from {action['validation_id']}, "
                   f"approved by {action['approval']['approver']}.")
    if not pending:
        if not actions:
            st.info("Nothing is waiting for approval.")
        return
    action, validation = pending[0], pending[0]["validation"]
    recommended = next((r for r in view.option_rows(plan) if r["recommended"]), None)
    with st.container(border=True):
        st.markdown("#### Approve stock transport order")
        st.markdown(f"**{validation['quantity']:g} t** from plant **{validation['source_plant']}** "
                    f"to plant **{validation['destination_plant']}**")
        st.markdown(f"{validation['validation_id']}: all business rules pass "
                    "(safety stock, arrival before stock-out, no over-transfer, plants match the case).")
        if recommended:
            st.markdown(f"Plan: {recommended['option']} → coverage {recommended['coverage_days']:g} "
                        f"of {recommended['needed_days']:g} days; deferred orders: {recommended['deferred_orders']}.")
        reason = st.text_input("Reason (required to reject)", key="reject-reason")
        approve, reject = st.columns(2)
        planner = st.session_state.get("planner", PLANNERS[0])
        if approve.button("Approve", key="approve", type="primary", disabled=case["running"], width="stretch"):
            clear.submit_decision(case["case_id"], validation["validation_id"], planner, "approved")
            st.session_state.was_running = True
            st.rerun()
        if reject.button("Reject", key="reject", disabled=case["running"] or not reason.strip(), width="stretch"):
            clear.submit_decision(case["case_id"], validation["validation_id"], planner, "rejected", reason.strip())
            st.rerun()


def documents_panel(case: dict) -> None:
    bundle = case["documents"]
    documents = view.document_lines(bundle["documents"], bundle["required_documents"], case["reconciliation"])
    if not case["reconciliation"]:
        st.caption("Not reconciled yet.")
    for document in documents:
        st.markdown(f"**{document['title']}**")
        if document["missing"]:
            st.error("Missing document.")
            continue
        st.html(document_html(document["lines"]))


def document_html(lines: list[dict]) -> str:
    mark_style = {
        "mismatch": "background: rgba(236,131,90,0.35); font-weight: 600;",
        "reference": "background: rgba(57,135,229,0.18);",
    }
    note = {"mismatch": "  ◀ differs from the PO", "reference": "  ◀ agrees with the PO"}
    rendered = []
    for line in lines:
        text = html.escape(line["text"])
        if line["mark"]:
            text = f'<span style="{mark_style[line["mark"]]}">{text}{note[line["mark"]]}</span>'
        rendered.append(text)
    return ('<pre style="font-family: ui-monospace, Consolas, monospace; font-size: 0.85rem; white-space: pre-wrap; '
            'margin: 0 0 1rem; padding: 0.75rem; border: 1px solid rgba(128,128,128,0.3); border-radius: 8px;">'
            + "\n".join(rendered) + "</pre>")


def stock_panel(case: dict) -> None:
    inventory = case["inventory"]
    st.markdown(f"**{inventory['material']}** · {inventory['sources']['stock']}")
    st.dataframe(pd.DataFrame([{
        "Plant": p["plant"], "Unrestricted (t)": p["unrestricted_t"], "In transit (t)": p["in_transit_t"],
        "Safety stock (t)": p["safety_stock_t"], "Use, all orders (t/day)": p["consumption_t_per_day"]["all"],
        "Use, critical + high (t/day)": p["consumption_t_per_day"]["critical_high"],
        "Use, critical (t/day)": p["consumption_t_per_day"]["critical"],
    } for p in inventory["plants"]]), hide_index=True, width="stretch")


main()
