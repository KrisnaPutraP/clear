"use client";

import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Compass,
  FileCheck2,
  FileText,
  GitBranch,
  Layers3,
  LoaderCircle,
  Package,
  Play,
  Radio,
  RefreshCw,
  ShieldCheck,
  Ship,
  TriangleAlert,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import type {
  Action,
  Assessment,
  Case,
  CaseStatus,
  CaseSummary,
  Event,
  Health,
  LogEntry,
} from "../lib/types";

const statuses: Record<CaseStatus, string> = {
  analyzing: "Analyzing",
  awaiting_approval: "Awaiting approval",
  executing: "Executing",
  monitoring: "Monitoring",
  needs_human_decision: "Needs a decision",
};
const eventTitles: Record<string, string> = {
  "S1-DOC-HOLD": "Customs document hold",
  "S1-ETA-SLIP": "Vessel ETA changed",
  "S2-CONGESTION": "Port congestion",
};
const priorities: Record<string, string> = {
  all: "All demand",
  critical_high: "Critical + high",
  critical: "Critical only",
};
const documentTitles: Record<string, string> = {
  commercial_invoice: "Commercial invoice",
  packing_list: "Packing list",
  bill_of_lading: "Bill of lading",
  certificate_of_analysis: "Certificate of analysis",
};
const number = (n: number) =>
  new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(n);
const time = (value: string) =>
  new Date(value).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
const date = (value: string) =>
  new Date(value).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
type Tab = "Overview" | "Documents" | "Inventory" | "Approval";

function Status({ status }: { status: CaseStatus }) {
  return (
    <span className={`status ${status}`}>
      <span className="status-dot" />
      {statuses[status] || status}
    </span>
  );
}

export default function Workspace() {
  const [health, setHealth] = useState<Health | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<Case | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [tab, setTab] = useState<Tab>("Overview");
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [pending, setPending] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [approver, setApprover] = useState("Rina Hartono");
  const mutationLock = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let cursor = 0;
    setLogs([]);

    async function poll() {
      try {
        const signal = AbortSignal.any([
          controller.signal,
          AbortSignal.timeout(15000),
        ]);
        const [nextHealth, nextEvents, nextCases] = await Promise.all([
          api<Health>("/health", { signal }),
          api<Event[]>("/events", { signal }),
          api<CaseSummary[]>("/cases", { signal }),
        ]);
        if (controller.signal.aborted) return;
        setHealth(nextHealth);
        setEvents(nextEvents);
        setCases(nextCases);
        if (!selectedId && nextCases.length) {
          setSelectedId(nextCases[0].case_id);
        } else if (selectedId) {
          if (!nextCases.some((c) => c.case_id === selectedId)) {
            setSelectedId(nextCases[0]?.case_id || "");
            setDetail(null);
          } else {
            const [nextCase, nextLogs] = await Promise.all([
              api<Case>(`/cases/${encodeURIComponent(selectedId)}`, { signal }),
              api<LogEntry[]>(
                `/cases/${encodeURIComponent(selectedId)}/log?after_seq=${cursor}`,
                { signal },
              ),
            ]);
            if (controller.signal.aborted) return;
            setDetail(nextCase);
            if (nextLogs.length) {
              cursor = nextLogs[nextLogs.length - 1].seq;
              setLogs((previous) => [...previous, ...nextLogs]);
            }
          }
        }
        setError("");
      } catch (cause) {
        if (!controller.signal.aborted)
          setError(
            cause instanceof Error ? cause.message : "Unable to reach CLEAR.",
          );
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          timer = setTimeout(poll, 2000);
        }
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [selectedId, refreshKey]);

  const activeCase = detail?.case_id === selectedId ? detail : null;
  const busy =
    pending || Boolean(health?.running) || Boolean(activeCase?.running);
  const disabled = busy || !health || Boolean(error);
  const awaiting = cases.filter((c) => c.status === "awaiting_approval").length;

  async function sendEvent(event: Event) {
    if (mutationLock.current) return;
    mutationLock.current = true;
    setPending(true);
    setActionError("");
    try {
      const result = await api<{ case_id: string }>(
        `/events/${encodeURIComponent(event.event_id)}`,
        { method: "POST" },
      );
      setSelectedId(result.case_id);
      setTab("Overview");
      setRefreshKey((k) => k + 1);
    } catch (cause) {
      setActionError(
        cause instanceof Error ? cause.message : "Could not send this event.",
      );
    } finally {
      mutationLock.current = false;
      setPending(false);
    }
  }

  async function decide(
    action: Action,
    decision: "approved" | "rejected",
    reason: string,
  ) {
    if (!activeCase || mutationLock.current) return;
    mutationLock.current = true;
    setPending(true);
    setActionError("");
    try {
      await api(`/cases/${encodeURIComponent(activeCase.case_id)}/decisions`, {
        method: "POST",
        body: JSON.stringify({
          validation_id: action.validation_id,
          approver,
          decision,
          reason: reason.trim() || null,
        }),
      });
      setTab("Overview");
      setRefreshKey((k) => k + 1);
    } catch (cause) {
      setActionError(
        cause instanceof Error
          ? cause.message
          : "Could not record your decision.",
      );
    } finally {
      mutationLock.current = false;
      setPending(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="CLEAR home">
          <span className="brand-icon">
            <Compass size={24} />
          </span>
          CLEAR<span className="brand-period">.</span>
        </a>
        <div className="workspace-label">PLANNER WORKSPACE</div>
        <div className="nav-current">
          <Layers3 size={17} />
          Exception workspace<span>{cases.length}</span>
        </div>
        <div className="sidebar-heading">
          YOUR CASES<span>{loading ? "…" : cases.length}</span>
        </div>
        <nav className="case-list" aria-label="Cases">
          {cases.map((item) => (
            <button
              key={item.case_id}
              className={`case-link ${selectedId === item.case_id ? "selected" : ""}`}
              onClick={() => {
                setSelectedId(item.case_id);
                setTab("Overview");
                setActionError("");
              }}
            >
              <span className="case-link-top">
                <Package size={15} />
                {item.case_id}
                <ChevronRight size={14} />
              </span>
              <span className="case-link-shipment">{item.shipment_id}</span>
              <span className={`case-link-status ${item.status}`}>
                {statuses[item.status]}
              </span>
            </button>
          ))}
          {!cases.length && (
            <p className="sidebar-empty">
              Cases will appear here when you send a logistics event.
            </p>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="guardrail">
            <ShieldCheck size={20} />
            <div>
              <strong>Human in control</strong>
              <p>Every ERP write needs your approval.</p>
            </div>
          </div>
          <label className="planner-label" htmlFor="planner">
            Demo planner
          </label>
          <select
            id="planner"
            value={approver}
            onChange={(e) => setApprover(e.target.value)}
            disabled={busy}
          >
            <option>Rina Hartono</option>
            <option>Bayu Pratama</option>
          </select>
          <div className="planner-caption">Fictional demo identities</div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <span>
            Operations <ChevronRight size={13} />
            <strong>Exception workspace</strong>
          </span>
          <div className="connection">
            <span
              className={`connection-dot ${error ? "offline" : health ? "online" : ""}`}
            />
            {error
              ? "Connection interrupted"
              : health
                ? "API connected"
                : "Connecting…"}
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">CROSS-BORDER OPERATIONS</div>
              <h1>Clarity through every exception.</h1>
              <p>
                Investigate the disruption. Understand the impact. Approve the
                next move.
              </p>
            </div>
            <div className="live-indicator">
              <Radio size={16} />
              {busy ? "Agents working" : "Workspace ready"}
            </div>
          </div>

          {health?.mode === "scripted" && (
            <div className="notice scripted">
              <TriangleAlert size={17} />
              <span>
                <strong>Scripted development mode.</strong> Agent responses
                follow predefined scenarios. This mode does not demonstrate live
                AI reasoning.
              </span>
            </div>
          )}
          {error && (
            <div className="notice error" role="alert">
              <TriangleAlert size={18} />
              <span>
                <strong>Updates paused.</strong> {error} Displayed data may be
                out of date.
              </span>
              <button onClick={() => setRefreshKey((k) => k + 1)}>
                <RefreshCw size={14} />
                Retry
              </button>
            </div>
          )}
          {actionError && (
            <div className="notice error" role="alert">
              <TriangleAlert size={18} />
              <span>{actionError}</span>
              <button
                onClick={() => setActionError("")}
                aria-label="Dismiss error"
              >
                <X size={16} />
              </button>
            </div>
          )}

          <section className="event-section" aria-labelledby="event-heading">
            <div className="section-heading">
              <h2 id="event-heading">
                <Radio size={17} />
                Logistics event feed{" "}
                <span className="subtle-tag">Simulated</span>
              </h2>
              <span>Send an event to start or update a case</span>
            </div>
            <div className="event-grid">
              {events.map((event, i) => {
                const etaNeedsCase =
                  event.type === "eta_change" &&
                  !cases.some((c) => c.shipment_id === event.shipment_id);
                const Icon =
                  event.type === "customs_document_hold"
                    ? FileText
                    : event.type === "eta_change"
                      ? Clock3
                      : Ship;
                return (
                  <button
                    className="event-card"
                    key={event.event_id}
                    disabled={disabled || etaNeedsCase}
                    onClick={() => void sendEvent(event)}
                    title={
                      etaNeedsCase
                        ? "Start the customs document hold case first."
                        : event.description
                    }
                  >
                    <div className="event-card-top">
                      <span className={`event-icon event-${i}`}>
                        <Icon size={21} />
                      </span>
                      <span className="event-scenario">
                        {event.scenario}
                        {event.type === "eta_change"
                          ? " · Follow-up"
                          : " · New exception"}
                      </span>
                      <ArrowUpRight size={17} className="event-arrow" />
                    </div>
                    <h3>
                      {eventTitles[event.event_id] ||
                        event.type.replaceAll("_", " ")}
                    </h3>
                    <p>{event.description}</p>
                    <div className="event-card-bottom">
                      <span>{event.shipment_id}</span>
                      <span>
                        {etaNeedsCase ? "Start S1 first" : "Send event"}
                        <Play size={11} />
                      </span>
                    </div>
                  </button>
                );
              })}
              {!events.length && (
                <div className="event-placeholder">
                  {loading
                    ? "Loading available events…"
                    : "Events are unavailable. Check your API connection."}
                </div>
              )}
            </div>
          </section>

          <div className="workspace-heading">
            <h2>Case workspace</h2>
            <div className="workspace-counts">
              <span>{cases.length} cases</span>
              <span className="divider" />
              <span className={awaiting ? "attention-text" : ""}>
                {awaiting} awaiting approval
              </span>
            </div>
          </div>

          {!activeCase ? (
            <section className="empty-workspace">
              <div className="empty-route">
                <span>
                  <Ship size={25} />
                </span>
                <i />
                <span className="route-middle">
                  <Compass size={30} />
                </span>
                <i />
                <span>
                  <Package size={25} />
                </span>
              </div>
              <span className="eyebrow">FROM DISRUPTION TO DECISION</span>
              <h2>
                {selectedId
                  ? "Opening your case…"
                  : "Your next move starts here."}
              </h2>
              <p>
                {selectedId
                  ? "Gathering the latest evidence, plan, and agent activity."
                  : "Choose a logistics event above. CLEAR will investigate the evidence and prepare a recovery plan for your review."}
              </p>
              <div className="empty-steps">
                <span>
                  <FileCheck2 size={15} />
                  Evidence
                </span>
                <ArrowRight size={13} />
                <span>
                  <Activity size={15} />
                  Impact
                </span>
                <ArrowRight size={13} />
                <span>
                  <ShieldCheck size={15} />
                  Approved action
                </span>
              </div>
            </section>
          ) : (
            <>
              <section className="case-banner">
                <div>
                  <span className="case-banner-id">{activeCase.case_id}</span>
                  <Status status={activeCase.status} />
                  {busy && <LoaderCircle size={15} className="spin" />}
                </div>
                <div className="case-route">
                  <Ship size={15} />
                  <strong>{activeCase.shipment.port_of_loading}</strong>
                  <ArrowRight size={14} />
                  <strong>{activeCase.shipment.port_of_discharge}</strong>
                  <span>{activeCase.shipment_id}</span>
                </div>
                <div className="case-eta">
                  <Clock3 size={14} />
                  ETA {date(activeCase.shipment.eta)}
                </div>
              </section>
              {activeCase.status_reason && (
                <div className="notice status-notice">
                  <TriangleAlert size={17} />
                  <span>{activeCase.status_reason}</span>
                </div>
              )}
              <div className="case-grid">
                <section className="detail-panel">
                  <div
                    className="tabs"
                    role="tablist"
                    aria-label="Case details"
                  >
                    {(
                      [
                        "Overview",
                        "Documents",
                        "Inventory",
                        "Approval",
                      ] as Tab[]
                    ).map((name) => (
                      <button
                        role="tab"
                        id={`tab-${name}`}
                        aria-selected={tab === name}
                        aria-controls="case-tabpanel"
                        tabIndex={tab === name ? 0 : -1}
                        key={name}
                        onKeyDown={(e) => {
                          const names: Tab[] = [
                            "Overview",
                            "Documents",
                            "Inventory",
                            "Approval",
                          ];
                          if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                            e.preventDefault();
                            const next =
                              names[
                                (names.indexOf(name) +
                                  (e.key === "ArrowRight" ? 1 : 3)) %
                                  4
                              ];
                            setTab(next);
                            document.getElementById(`tab-${next}`)?.focus();
                          }
                        }}
                        className={tab === name ? "active" : ""}
                        onClick={() => setTab(name)}
                      >
                        {name}
                        {name === "Approval" &&
                          activeCase.status === "awaiting_approval" && (
                            <span className="tab-dot" />
                          )}
                      </button>
                    ))}
                  </div>
                  <div
                    className="panel-content"
                    role="tabpanel"
                    id="case-tabpanel"
                    aria-labelledby={`tab-${tab}`}
                  >
                    {tab === "Overview" && (
                      <Overview
                        item={activeCase}
                        onReview={() => setTab("Approval")}
                      />
                    )}
                    {tab === "Documents" && <Documents item={activeCase} />}
                    {tab === "Inventory" && <Inventory item={activeCase} />}
                    {tab === "Approval" && (
                      <div className="approval-list">
                        <div className="panel-heading">
                          <ShieldCheck size={20} />
                          <div>
                            <h3>Decision desk</h3>
                            <p>
                              Review the validated action before an ERP write.
                            </p>
                          </div>
                        </div>
                        {!activeCase.plan?.actions.length ? (
                          <div className="panel-empty">
                            No transfer is awaiting approval. Check the plan for
                            monitoring instructions or a decision that needs
                            your attention.
                          </div>
                        ) : (
                          activeCase.plan.actions.map((action) => (
                            <Approval
                              key={action.validation_id}
                              action={action}
                              caseItem={activeCase}
                              disabled={disabled}
                              approver={approver}
                              onDecision={decide}
                            />
                          ))
                        )}
                      </div>
                    )}
                  </div>
                </section>
                <Timeline entries={logs} running={activeCase.running} />
              </div>
            </>
          )}

          <footer>
            <span>
              <ShieldCheck size={14} />
              Evidence-backed plans. Human-approved actions.
            </span>
            <span>Synthetic demo data · {health?.model || "CLEAR"}</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

function Overview({ item, onReview }: { item: Case; onReview: () => void }) {
  const plan = item.plan;
  if (!plan)
    return (
      <div className="analysis-state">
        <span className="analysis-icon">
          {item.running ? (
            <LoaderCircle size={30} className="spin" />
          ) : (
            <TriangleAlert size={30} />
          )}
        </span>
        <h3>
          {item.running
            ? "Connecting the evidence."
            : "No recovery plan available."}
        </h3>
        <p>
          {item.running
            ? "The agents are investigating this exception. Follow their progress in the activity timeline."
            : "Review the case status and activity timeline for the reason."}
        </p>
      </div>
    );
  const impact = plan.impact;
  return (
    <>
      <div className="panel-heading">
        <span className="eyebrow">EXCEPTION BRIEF</span>
        <span className="source-label">{item.shipment_id}</span>
      </div>
      <h3 className="exception-title">{plan.exception}</h3>
      <div className="metric-grid">
        <Metric
          label="Resolution estimate"
          value={number(impact.prediction.predicted_days)}
          unit="days"
          note={impact.prediction.source}
        />
        <Metric
          label="Current coverage"
          value={number(impact.coverage_days)}
          unit="days"
          note={`${number(impact.required_coverage_days)} days required`}
        />
        <Metric
          label="Current shortage"
          value={number(impact.shortage_t)}
          unit="t"
          note="Before recovery"
          warning={!impact.covered}
        />
      </div>
      {impact.prediction.basis.fallback_reason && (
        <div className="notice scripted">
          <TriangleAlert size={16} />
          <span>
            SAP-RPT is unavailable. This estimate uses the baseline median.
          </span>
        </div>
      )}
      <div className="recommendation">
        <div className="recommendation-icon">
          <GitBranch size={20} />
        </div>
        <div>
          <span className="eyebrow">RECOMMENDED NEXT MOVE</span>
          <p>{plan.recommendation}</p>
          {item.status === "awaiting_approval" && (
            <button onClick={onReview}>
              Review transfer <ArrowRight size={14} />
            </button>
          )}
        </div>
      </div>
      {plan.escalation && (
        <div className="escalation">
          <TriangleAlert size={18} />
          <div>
            <strong>A decision needs your attention</strong>
            <p>{plan.escalation}</p>
          </div>
        </div>
      )}
      <div className="subsection-heading">
        <h4>Recovery options</h4>
        <span>Calculated by tools</span>
      </div>
      <div className="options">
        <Option name="Current plan" assessment={impact} recommended={false} />
        {plan.options.map((option) => (
          <Option
            key={option.name}
            name={option.name}
            assessment={option.assessment}
            recommended={option.name === plan.recommended_option}
            note={option.note}
            valid={option.validation?.valid}
          />
        ))}
      </div>
      <div className="subsection-heading">
        <h4>Supporting evidence</h4>
        <span>{plan.evidence.length} findings</span>
      </div>
      <div className="evidence-list">
        {plan.evidence.map((evidence, i) => (
          <div key={i}>
            <CheckCircle2 size={15} />
            <div>
              <p>{evidence.fact}</p>
              <span>{evidence.source}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="next-check">
        <Radio size={17} />
        <div>
          <strong>What happens next</strong>
          <p>{plan.next_check}</p>
        </div>
      </div>
    </>
  );
}

function Metric({
  label,
  value,
  unit,
  note,
  warning = false,
}: {
  label: string;
  value: string;
  unit: string;
  note: string;
  warning?: boolean;
}) {
  return (
    <div className={`metric ${warning ? "metric-warning" : ""}`}>
      <span>{label}</span>
      <strong>
        {value}
        <small>{unit}</small>
      </strong>
      <p>{note}</p>
    </div>
  );
}

function Option({
  name,
  assessment,
  recommended,
  note,
  valid,
}: {
  name: string;
  assessment: Assessment;
  recommended: boolean;
  note?: string;
  valid?: boolean;
}) {
  return (
    <div className={`option ${recommended ? "recommended" : ""}`}>
      <div className="option-title">
        <strong>{name}</strong>
        {recommended && (
          <span>
            <Check size={12} />
            Recommended
          </span>
        )}
      </div>
      <div className="option-meta">
        <span>
          {priorities[assessment.priority_level] || assessment.priority_level}
        </span>
        <span>
          {assessment.transfer
            ? `${number(assessment.transfer.quantity_t)} t from ${assessment.transfer.source_plant}`
            : "No transfer"}
        </span>
        <span className={assessment.covered ? "covered" : "short"}>
          {assessment.covered
            ? "Covered"
            : `${number(assessment.shortage_t)} t short`}
        </span>
      </div>
      <div className="coverage-bar">
        <span
          style={{
            width: `${assessment.required_coverage_days > 0 ? Math.min(100, Math.max(0, (assessment.coverage_days / assessment.required_coverage_days) * 100)) : 100}%`,
          }}
        />
      </div>
      <div className="coverage-caption">
        <span>{number(assessment.coverage_days)} days coverage</span>
        <span>{number(assessment.required_coverage_days)} required</span>
      </div>
      {assessment.transfer && (
        <p className="option-note">
          Transfer cost: ${number(assessment.transfer.cost_usd)} · Lead time:{" "}
          {number(assessment.transfer.lead_time_days)} days
        </p>
      )}
      {assessment.deferred_orders.length > 0 && (
        <p className="option-note">
          Deferred:{" "}
          {assessment.deferred_orders.map((o) => o.order_id).join(", ")}
        </p>
      )}
      {valid === false && (
        <p className="validation-rejected">
          <X size={13} />
          Rejected by validator
        </p>
      )}
      {note && <p className="option-note">{note}</p>}
    </div>
  );
}

function Documents({ item }: { item: Case }) {
  return (
    <>
      <div className="panel-heading">
        <FileText size={20} />
        <div>
          <h3>Shipping evidence</h3>
          <p>Source documents with reconciled discrepancies highlighted.</p>
        </div>
      </div>
      {item.documents.required_documents.map((type) => {
        const doc = item.documents.documents.find(
          (d) => d.document_type === type,
        );
        const findings =
          item.reconciliation?.discrepancies.filter((d) =>
            d.mismatched_documents.includes(type),
          ) || [];
        return (
          <details className="document" key={type} open={findings.length > 0}>
            <summary>
              <span>
                <FileText size={17} />
                {documentTitles[type] || type}
              </span>
              <span
                className={findings.length || !doc ? "short" : "source-label"}
              >
                {!doc
                  ? "Missing"
                  : findings.length
                    ? "Discrepancy"
                    : item.reconciliation
                      ? "Reviewed"
                      : "Available"}
                <ChevronRight size={14} />
              </span>
            </summary>
            {doc ? (
              <pre>
                {doc.text.split("\n").map((line, i) => {
                  const extraction =
                    item.reconciliation?.verified_extractions.find(
                      (e) =>
                        e.document_type === type &&
                        e.quote.trim() === line.trim() &&
                        findings.some((f) => f.field === e.field),
                    );
                  return (
                    <span key={i} className={extraction ? "doc-mismatch" : ""}>
                      {line}
                      {"\n"}
                    </span>
                  );
                })}
              </pre>
            ) : (
              <p className="missing-document">
                The required document is missing from the connected records.
              </p>
            )}
            {findings.length > 0 && (
              <div className="document-findings">
                <TriangleAlert size={14} />
                Mismatch: {findings.map((f) => f.field).join(", ")}
              </div>
            )}
          </details>
        );
      })}
      {!item.reconciliation && (
        <p className="panel-footnote">
          Document reconciliation has not been performed for this case.
        </p>
      )}
    </>
  );
}

function Inventory({ item }: { item: Case }) {
  return (
    <>
      <div className="panel-heading">
        <Package size={20} />
        <div>
          <h3>Material {item.inventory.material}</h3>
          <p>
            Stock position from S/4HANA (mock). All quantities are in tonnes.
          </p>
        </div>
      </div>
      {item.inventory.plants.map((plant) => (
        <div className="plant" key={plant.plant}>
          <div className="plant-heading">
            <h4>Plant {plant.plant}</h4>
            <span
              className={
                plant.unrestricted_t < plant.safety_stock_t
                  ? "short"
                  : "covered"
              }
            >
              {plant.unrestricted_t < plant.safety_stock_t
                ? "Below safety stock"
                : "Above safety threshold"}
            </span>
          </div>
          <div className="metric-grid">
            <Metric
              label="Unrestricted"
              value={number(plant.unrestricted_t)}
              unit="t"
              note="Available stock"
            />
            <Metric
              label="Safety stock"
              value={number(plant.safety_stock_t)}
              unit="t"
              note="Protected threshold"
            />
            <Metric
              label="In transit"
              value={number(plant.in_transit_t)}
              unit="t"
              note="Not physically received"
            />
          </div>
          <div className="stock-consumption">
            <span>Daily use · all demand</span>
            <strong>{number(plant.consumption_t_per_day.all)} t/day</strong>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Priority</th>
                  <th>Use / day</th>
                </tr>
              </thead>
              <tbody>
                {plant.orders.map((order) => (
                  <tr key={order.order_id}>
                    <td>
                      <strong>{order.order_id}</strong>
                      <span>{order.product}</span>
                    </td>
                    <td>
                      <span className={`priority ${order.priority}`}>
                        {order.priority}
                      </span>
                    </td>
                    <td>{number(order.consumption_t_per_day)} t</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </>
  );
}

function Approval({
  action,
  caseItem,
  disabled,
  approver,
  onDecision,
}: {
  action: Action;
  caseItem: Case;
  disabled: boolean;
  approver: string;
  onDecision: (
    action: Action,
    decision: "approved" | "rejected",
    reason: string,
  ) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const valid = action.validation;
  const isPending =
    action.status === "awaiting_approval" &&
    caseItem.status === "awaiting_approval" &&
    action.approval?.decision !== "rejected";
  return (
    <div className="approval-card">
      <div className="approval-card-heading">
        <span className="approval-shield">
          <ShieldCheck size={24} />
        </span>
        <div>
          <h3>Stock transport order</h3>
          <p>
            {action.validation_id} ·{" "}
            {valid.valid ? "Validation passed" : "Validation rejected"}
          </p>
        </div>
      </div>
      <div className="transfer-route">
        <div>
          <span>FROM</span>
          <strong>Plant {valid.source_plant}</strong>
        </div>
        <ArrowRight size={20} />
        <div>
          <span>TO</span>
          <strong>Plant {valid.destination_plant}</strong>
        </div>
        <div className="transfer-quantity">
          <strong>
            {number(valid.quantity)} <small>t</small>
          </strong>
        </div>
      </div>
      <p>{caseItem.plan?.recommendation}</p>
      <p className="panel-footnote">
        Quantity and route come from the validation record. Stock is rechecked
        before the order is created.
      </p>
      {action.status === "executed" ? (
        <div className="approval-executed">
          <CheckCircle2 size={18} />
          <div>
            <strong>
              Order created: {action.sto?.purchase_order || "See timeline"}
            </strong>
            <p>
              Approved by {action.approval?.approver || "the planner"}. Stock is
              in transit until goods receipt.
            </p>
          </div>
        </div>
      ) : action.approval?.decision === "rejected" ? (
        <div className="notice scripted">
          This transfer was rejected by {action.approval.approver}.
        </div>
      ) : !isPending ? (
        <div className="panel-empty">
          This plan is not currently accepting a decision.
        </div>
      ) : (
        <>
          <label
            className="reason-label"
            htmlFor={`reason-${action.validation_id}`}
          >
            Decision note <span>Required for rejection</span>
          </label>
          <textarea
            id={`reason-${action.validation_id}`}
            maxLength={2000}
            placeholder="Add context for your decision…"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={disabled}
          />
          <div className="approval-buttons">
            <button
              className="reject-button"
              disabled={disabled || !reason.trim()}
              onClick={() => void onDecision(action, "rejected", reason)}
            >
              <X size={16} />
              Reject
            </button>
            <button
              className="approve-button"
              disabled={disabled || !valid.valid}
              onClick={() => void onDecision(action, "approved", reason)}
            >
              <Check size={16} />
              Approve transfer
            </button>
          </div>
          <p className="approval-signature">
            Decision will be recorded as <strong>{approver}</strong>.
          </p>
        </>
      )}
    </div>
  );
}

function Timeline({
  entries,
  running,
}: {
  entries: LogEntry[];
  running: boolean;
}) {
  const scroll = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(() => {
    if (follow.current && scroll.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [entries.length]);
  return (
    <aside className="timeline-panel">
      <div className="timeline-heading">
        <h3>
          <Activity size={17} />
          Agent activity
        </h3>
        <span className={running ? "activity-live" : "source-label"}>
          {running ? "Live" : `${entries.length} entries`}
        </span>
      </div>
      <p className="timeline-caption">Every step, with its source.</p>
      <div
        className="timeline-scroll"
        ref={scroll}
        onScroll={(e) => {
          const element = e.currentTarget;
          follow.current =
            element.scrollHeight - element.scrollTop - element.clientHeight <
            100;
        }}
        role="log"
        aria-label="Agent activity timeline"
        aria-relevant="additions"
        aria-live="off"
      >
        {entries.map((entry) => (
          <div className={`timeline-entry ${entry.flag || ""}`} key={entry.seq}>
            <span className="timeline-node">
              {entry.flag === "rejected" || entry.flag === "error" ? (
                <X size={10} />
              ) : entry.flag === "write" ? (
                <Check size={10} />
              ) : null}
            </span>
            <div className="timeline-entry-heading">
              <strong>{entry.actor}</strong>
              <time dateTime={entry.at}>{time(entry.at)}</time>
            </div>
            {entry.flag && (
              <span className="timeline-flag">
                {entry.flag === "rejected"
                  ? "Validator rejected"
                  : entry.flag.replaceAll("_", " ")}
              </span>
            )}
            <p>{entry.summary}</p>
            {entry.source && (
              <div className="timeline-source">{entry.source}</div>
            )}
          </div>
        ))}
        {!entries.length && (
          <div className="timeline-empty">Waiting for the first activity…</div>
        )}
        {running && (
          <div className="timeline-working">
            <LoaderCircle size={14} className="spin" />
            Agents are working…
          </div>
        )}
      </div>
      <div className="timeline-bottom">
        <ShieldCheck size={13} />
        Tool results and decisions are recorded.
      </div>
    </aside>
  );
}
