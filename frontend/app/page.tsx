"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  FileCheck2,
  FileText,
  GitBranch,
  Info,
  Layers3,
  Menu,
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
const statusDetails: Record<
  CaseStatus,
  { icon: typeof Activity; description: string }
> = {
  analyzing: {
    icon: Activity,
    description:
      "CLEAR is investigating. You can review the evidence while the agents work.",
  },
  awaiting_approval: {
    icon: ShieldCheck,
    description:
      "Your approval is needed before CLEAR can create this transfer.",
  },
  executing: {
    icon: Package,
    description:
      "Approval received. CLEAR is creating the order and checking stock.",
  },
  monitoring: {
    icon: CheckCircle2,
    description:
      "No decision is pending. Open monitoring to review the latest records and follow-up.",
  },
  needs_human_decision: {
    icon: TriangleAlert,
    description:
      "A planner needs to decide the next step. Review the recommendation below.",
  },
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
type Tab = "Overview" | "Documents" | "Inventory" | "Approval" | "Monitoring";
const tabs: Tab[] = [
  "Overview",
  "Documents",
  "Inventory",
  "Approval",
  "Monitoring",
];
const tabDescriptions: Record<Tab, string> = {
  Overview:
    "Understand the disruption, compare recovery options, and see the next step.",
  Documents:
    "Compare shipping evidence against the purchase order to find what does not match.",
  Inventory:
    "Check available stock, safety thresholds, and which orders are affected.",
  Approval:
    "Review the validated transfer and record your decision before an ERP write.",
  Monitoring:
    "Review the latest shipment and stock records, and the follow-up needed for this case.",
};

function ClearMark({
  active = false,
  size = 28,
}: {
  active?: boolean;
  size?: number;
}) {
  return (
    <span
      className="clear-mark"
      data-active={active}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <img
        className="compass-still"
        src={active ? "/clear-compass-still.svg" : "/clear-compass.svg"}
        width={size}
        height={size}
        alt=""
        draggable={false}
      />
      {active && (
        <img
          className="compass-animated"
          src="/clear-compass-loading.svg"
          width={size}
          height={size}
          alt=""
          draggable={false}
        />
      )}
    </span>
  );
}

function Notice({
  tone = "info",
  title,
  children,
  onDismiss,
}: {
  tone?: "info" | "success" | "warning" | "error";
  title: string;
  children: ReactNode;
  onDismiss?: () => void;
}) {
  const Icon =
    tone === "success" ? CheckCircle2 : tone === "info" ? Info : TriangleAlert;
  return (
    <div
      className={`notice notice-${tone}`}
      role={tone === "error" ? "alert" : "status"}
    >
      <Icon size={20} aria-hidden="true" />
      <div className="notice-copy">
        <strong>{title}</strong>
        <div>{children}</div>
      </div>
      {onDismiss && (
        <button onClick={onDismiss} aria-label="Dismiss notification">
          <X size={17} />
        </button>
      )}
    </div>
  );
}

function Status({ status }: { status: CaseStatus }) {
  const Icon = statusDetails[status].icon;
  return (
    <span className={`status ${status}`}>
      <Icon size={14} aria-hidden="true" />
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
  const [feedback, setFeedback] = useState<{
    title: string;
    message: string;
  } | null>(null);
  const [eventsExpanded, setEventsExpanded] = useState(true);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const navigationButton = useRef<HTMLButtonElement>(null);
  const navigationClose = useRef<HTMLButtonElement>(null);
  const mutationLock = useRef(false);

  function openCaseTab(next: Tab) {
    setTab(next);
    requestAnimationFrame(() => {
      const panel = document.getElementById("case-tabpanel");
      panel?.focus({ preventScroll: true });
      panel?.scrollIntoView({ block: "nearest" });
    });
  }

  useEffect(() => {
    if (!navigationOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    navigationClose.current?.focus();
    function closeOnEscape(event: KeyboardEvent) {
      const pickerOpen =
        CSS.supports("selector(select:open)") &&
        document.querySelector("select:open");
      if (event.defaultPrevented || pickerOpen) return;
      if (event.key === "Escape") {
        setNavigationOpen(false);
        navigationButton.current?.focus();
      }
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = previousOverflow;
    };
  }, [navigationOpen]);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1101px)");
    const closeOnDesktop = () => {
      if (desktop.matches) setNavigationOpen(false);
    };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);

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
          setEventsExpanded(false);
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
            setCases((previous) =>
              previous.map((item) =>
                item.case_id === nextCase.case_id
                  ? { ...item, status: nextCase.status }
                  : item,
              ),
            );
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
  const attention = cases.filter(
    (c) =>
      c.status === "awaiting_approval" || c.status === "needs_human_decision",
  );

  async function sendEvent(event: Event) {
    if (mutationLock.current) return;
    mutationLock.current = true;
    setPending(true);
    setActionError("");
    setFeedback(null);
    try {
      const result = await api<{ case_id: string }>(
        `/events/${encodeURIComponent(event.event_id)}`,
        { method: "POST" },
      );
      setSelectedId(result.case_id);
      setEventsExpanded(false);
      setFeedback({
        title: "Event received",
        message: `${eventTitles[event.event_id] || "Logistics event"} was submitted. See the case below for the latest result.`,
      });
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
    setFeedback(null);
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
      setDetail((previous) =>
        previous
          ? {
              ...previous,
              status:
                decision === "approved" ? "executing" : "needs_human_decision",
              running: decision === "approved",
            }
          : previous,
      );
      setTab(decision === "approved" ? "Approval" : "Overview");
      setFeedback({
        title:
          decision === "approved" ? "Transfer approved" : "Transfer rejected",
        message:
          decision === "approved"
            ? `Your approval was recorded as ${approver}. Follow the case for order creation and stock verification.`
            : "Your reason has been recorded. This case now needs a planner's decision.",
      });
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

  const eventSimulator = (
    <section
      className="event-section"
      id="event-simulator"
      aria-labelledby="event-heading"
    >
      <button
        className="event-toggle"
        aria-expanded={eventsExpanded}
        aria-controls="event-options"
        onClick={() => setEventsExpanded(!eventsExpanded)}
      >
        <div className="section-heading">
          <h2 id="event-heading">
            <Radio size={17} />
            Demo event simulator <span className="subtle-tag">Simulated</span>
          </h2>
          <span>
            {eventsExpanded
              ? "Choose an event to start or reassess a case"
              : "Start another case or send an ETA update"}
          </span>
        </div>
        <ChevronDown size={18} />
      </button>
      <div className="event-grid" id="event-options" hidden={!eventsExpanded}>
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
                {eventTitles[event.event_id] || event.type.replaceAll("_", " ")}
              </h3>
              <p>{event.description}</p>
              <div className="event-card-bottom">
                <span>{event.shipment_id}</span>
                <span>
                  {etaNeedsCase
                    ? "Start the document case first"
                    : busy
                      ? "Wait for the current run"
                      : event.type === "eta_change"
                        ? "Reassess case"
                        : "Start investigation"}
                  <Play size={11} />
                </span>
              </div>
            </button>
          );
        })}
        {!events.length && (
          <div className="event-placeholder">
            {loading ? (
              <>
                <ClearMark active size={32} />
                Loading available events…
              </>
            ) : (
              "Events are unavailable. Check your API connection."
            )}
          </div>
        )}
      </div>
    </section>
  );

  return (
    <div
      className={`app-shell ${activeCase ? "has-case" : ""} ${navigationOpen ? "navigation-open" : ""}`}
    >
      <a className="skip-link" href="#workspace">
        Skip to case workspace
      </a>
      {navigationOpen && (
        <button
          className="navigation-backdrop"
          aria-label="Close navigation"
          tabIndex={-1}
          onClick={() => {
            setNavigationOpen(false);
            navigationButton.current?.focus();
          }}
        />
      )}
      <aside
        className="sidebar"
        id="planner-navigation"
        aria-label="Planner navigation"
      >
        <button
          ref={navigationClose}
          className="navigation-close"
          onClick={() => {
            setNavigationOpen(false);
            navigationButton.current?.focus();
          }}
          aria-label="Close navigation"
        >
          <X size={20} />
        </button>
        <a className="brand" href="/" aria-label="CLEAR home">
          <span className="brand-icon">
            <ClearMark />
          </span>
          CLEAR<span className="brand-period">.</span>
        </a>
        <div className="workspace-label">Planner workspace</div>
        <div className="nav-current">
          <Layers3 size={17} />
          Exception workspace
        </div>
        <div className="sidebar-heading">
          Cases<span>{loading ? "…" : cases.length}</span>
        </div>
        <nav className="case-list" aria-label="Cases">
          {cases.map((item) => (
            <button
              key={item.case_id}
              className={`case-link ${selectedId === item.case_id ? "selected" : ""}`}
              aria-current={selectedId === item.case_id ? "page" : undefined}
              onClick={() => {
                setSelectedId(item.case_id);
                setTab("Overview");
                setActionError("");
                setFeedback(null);
                setNavigationOpen(false);
              }}
            >
              <span className="case-link-top">
                <Package size={15} />
                {item.case_id}
                <ChevronRight size={14} />
              </span>
              <span className="case-link-shipment">{item.shipment_id}</span>
              <Status status={item.status} />
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
            aria-describedby="planner-caption"
            value={approver}
            onChange={(e) => setApprover(e.target.value)}
            disabled={busy}
          >
            <option>Rina Hartono</option>
            <option>Bayu Pratama</option>
          </select>
          <div className="planner-caption" id="planner-caption">
            Fictional demo identities
          </div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <button
            ref={navigationButton}
            className="navigation-toggle"
            aria-expanded={navigationOpen}
            aria-controls="planner-navigation"
            aria-label="Open navigation"
            onClick={() => setNavigationOpen(!navigationOpen)}
          >
            <Menu size={20} />
          </button>
          <a className="mobile-brand" href="/" aria-label="CLEAR home">
            <ClearMark size={23} /> CLEAR.
          </a>
          <span>
            Operations <ChevronRight size={13} />
            <strong>Exception workspace</strong>
          </span>
          <div className="topbar-status">
            {attention.length > 0 && (
              <button
                className="attention-button"
                onClick={() => {
                  setSelectedId(attention[0].case_id);
                  setTab(
                    attention[0].status === "awaiting_approval"
                      ? "Approval"
                      : "Overview",
                  );
                }}
              >
                <TriangleAlert size={15} />
                {attention.length} needs attention
              </button>
            )}
            <div className="connection" role="status">
              <span
                className={`connection-dot ${error ? "offline" : health ? "online" : ""}`}
              />
              {error
                ? "Connection interrupted"
                : health
                  ? "API connected"
                  : "Connecting…"}
            </div>
          </div>
        </header>
        <main inert={navigationOpen || undefined}>
          <div className="page-heading">
            <div>
              <h1>Exception workspace</h1>
              <p>
                See what is at risk. Review the evidence. Decide the next move.
              </p>
            </div>
            <div className="workspace-tools">
              <a
                className="simulator-shortcut"
                href="#event-simulator"
                onClick={() => setEventsExpanded(true)}
              >
                <Radio size={16} />
                Simulate event
              </a>
              {(busy || !activeCase) && (
                <div className="live-indicator">
                  {busy ? (
                    <ClearMark active size={22} />
                  ) : (
                    <ShieldCheck size={16} />
                  )}
                  {busy
                    ? "Agents working"
                    : attention.length
                      ? "Decision pending"
                      : "Ready for the next event"}
                </div>
              )}
            </div>
          </div>

          {health?.mode === "scripted" && (
            <div className="environment-notice">
              <Notice title="Scripted development mode.">
                Predefined agent responses and synthetic data. Live AI reasoning
                is off.
              </Notice>
            </div>
          )}
          {error && (
            <Notice
              tone="error"
              title="Connection interrupted. Updates paused."
            >
              Displayed data may be out of date. Decisions are disabled until
              the connection recovers.
              <button onClick={() => setRefreshKey((k) => k + 1)}>
                <RefreshCw size={14} />
                Retry
              </button>
              <details className="error-details">
                <summary>Technical details</summary>
                {error}
              </details>
            </Notice>
          )}
          {actionError && (
            <Notice
              tone="error"
              title="Your request was not completed"
              onDismiss={() => setActionError("")}
            >
              Review the latest case state before trying again.
              <details className="error-details">
                <summary>Request details</summary>
                {actionError}
              </details>
            </Notice>
          )}
          {feedback && !actionError && (
            <Notice
              tone="success"
              title={feedback.title}
              onDismiss={() => setFeedback(null)}
            >
              {feedback.message}
            </Notice>
          )}

          {!activeCase && eventSimulator}

          <div className="workspace-heading" id="workspace" tabIndex={-1}>
            <h2>Case workspace</h2>
            <div className="workspace-counts">
              <span>
                {cases.length} {cases.length === 1 ? "case" : "cases"}
              </span>
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
                  <ClearMark
                    active={Boolean(selectedId) || loading}
                    size={42}
                  />
                </span>
                <i />
                <span>
                  <Package size={25} />
                </span>
              </div>
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
              <CaseProgress
                item={activeCase}
                entries={logs}
                onNavigate={openCaseTab}
              />
              <div className="case-grid">
                <section className="detail-panel">
                  <div
                    className="tabs"
                    role="tablist"
                    aria-label="Case details"
                  >
                    {tabs.map((name) => (
                      <button
                        role="tab"
                        id={`tab-${name}`}
                        aria-selected={tab === name}
                        aria-controls="case-tabpanel"
                        tabIndex={tab === name ? 0 : -1}
                        key={name}
                        onKeyDown={(e) => {
                          if (
                            ["ArrowRight", "ArrowLeft", "Home", "End"].includes(
                              e.key,
                            )
                          ) {
                            e.preventDefault();
                            const next =
                              e.key === "Home"
                                ? tabs[0]
                                : e.key === "End"
                                  ? tabs[tabs.length - 1]
                                  : tabs[
                                      (tabs.indexOf(name) +
                                        (e.key === "ArrowRight"
                                          ? 1
                                          : tabs.length - 1)) %
                                        tabs.length
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
                            <span className="tab-count" aria-label="1 pending">
                              1
                            </span>
                          )}
                        {name === "Documents" &&
                          Boolean(
                            activeCase.reconciliation?.discrepancies.length,
                          ) && (
                            <TriangleAlert
                              size={13}
                              aria-label="Discrepancy found"
                            />
                          )}
                      </button>
                    ))}
                  </div>
                  <div
                    className="panel-content"
                    key={`${activeCase.case_id}-${tab}`}
                    role="tabpanel"
                    tabIndex={0}
                    id="case-tabpanel"
                    aria-labelledby={`tab-${tab}`}
                  >
                    <p className="tab-description">{tabDescriptions[tab]}</p>
                    {tab === "Overview" && <Overview item={activeCase} />}
                    {tab === "Documents" && <Documents item={activeCase} />}
                    {tab === "Inventory" && <Inventory item={activeCase} />}
                    {tab === "Monitoring" && <Monitoring item={activeCase} />}
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
                              error={actionError}
                              onDecision={decide}
                            />
                          ))
                        )}
                      </div>
                    )}
                  </div>
                </section>
                <div className="case-rail">
                  {activeCase.plan && (
                    <section
                      className="case-evidence"
                      aria-labelledby="evidence-heading"
                    >
                      <div className="subsection-heading">
                        <h3 id="evidence-heading">Supporting evidence</h3>
                        <span>{activeCase.plan.evidence.length} findings</span>
                      </div>
                      <div className="evidence-list">
                        {activeCase.plan.evidence.map((evidence, i) => (
                          <div key={i}>
                            <CheckCircle2 size={15} />
                            <div>
                              <p>{evidence.fact}</p>
                              <span>{evidence.source}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}
                  <Timeline
                    key={activeCase.case_id}
                    entries={logs}
                    running={activeCase.running}
                  />
                  {activeCase.plan && (
                    <section className="next-check">
                      <Radio size={17} />
                      <div>
                        <h3>What happens next</h3>
                        <p>{activeCase.plan.next_check}</p>
                        <button
                          className="text-button"
                          onClick={() => openCaseTab("Monitoring")}
                        >
                          View monitoring <ArrowRight size={14} />
                        </button>
                      </div>
                    </section>
                  )}
                </div>
              </div>
            </>
          )}

          {activeCase && eventSimulator}

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

function CaseProgress({
  item,
  entries,
  onNavigate,
}: {
  item: Case;
  entries: LogEntry[];
  onNavigate: (tab: Tab) => void;
}) {
  const latest = entries.findLast((entry) => entry.kind === "tool");
  const phase =
    item.status === "analyzing" || !item.plan
      ? entries.some(
          (e) => e.actor === "Impact & Options" || e.actor === "Action",
        )
        ? 1
        : 0
      : item.status === "monitoring"
        ? 3
        : 2;
  const active = item.running;
  const StageIcon = statusDetails[item.status].icon;
  const steps = [
    "Investigate",
    "Assess impact",
    item.status === "needs_human_decision"
      ? "Planner decision"
      : item.status === "monitoring" && !item.plan?.actions.length
        ? "No action needed"
        : "Review & approve",
    "Monitor",
  ];
  const destinations: Tab[] = [
    "Documents",
    "Overview",
    item.status === "needs_human_decision" || !item.plan?.actions.length
      ? "Overview"
      : "Approval",
    "Monitoring",
  ];
  return (
    <section
      className={`case-progress ${item.status}`}
      aria-label="Case progress"
    >
      <div className="case-next-step" role="status" aria-atomic="true">
        <span className="case-state-icon">
          {active ? <ClearMark active size={32} /> : <StageIcon size={24} />}
        </span>
        <div>
          <h2>
            {active
              ? item.status === "executing"
                ? "Putting your approved plan into action"
                : "CLEAR is working on this case"
              : statuses[item.status]}
          </h2>
          <p>{item.status_reason || statusDetails[item.status].description}</p>
        </div>
        {item.status === "awaiting_approval" && !active && (
          <button
            className="primary-button"
            onClick={() => onNavigate("Approval")}
          >
            Review transfer <ArrowRight size={16} />
          </button>
        )}
        {item.status === "monitoring" && !active && (
          <button
            className="primary-button"
            onClick={() => onNavigate("Monitoring")}
          >
            View monitoring <ArrowRight size={16} />
          </button>
        )}
      </div>
      <ol className="workflow-steps">
        {steps.map((step, i) => (
          <li
            key={i}
            className={i < phase ? "complete" : i === phase ? "current" : ""}
            aria-current={i === phase ? "step" : undefined}
          >
            <span>{i < phase ? <Check size={13} /> : i + 1}</span>
            <button onClick={() => onNavigate(destinations[i])}>{step}</button>
          </li>
        ))}
      </ol>
      {active && (
        <div className="run-update">
          <span className="working-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <p>
            <strong>{latest?.actor || "Orchestrator"}</strong>
            {latest
              ? ` · ${latest.summary}`
              : " · Starting the investigation. Live results will appear as each tool finishes."}
          </p>
        </div>
      )}
      {active && item.plan && (
        <p className="updating-plan">
          <Info size={14} />
          The plan below is from the previous run. CLEAR is reassessing it;
          decisions are paused.
        </p>
      )}
    </section>
  );
}

function Monitoring({ item }: { item: Case }) {
  const plan = item.plan;
  const executed =
    plan?.actions.filter((action) => action.status === "executed") || [];
  return (
    <div className="monitoring-view">
      {item.status !== "monitoring" && (
        <Notice
          title={
            item.running
              ? "Case reassessment in progress"
              : "Monitoring is not the current stage"
          }
        >
          {item.running
            ? "The records below may change when the current run finishes."
            : `This case is ${statuses[item.status].toLowerCase()}. Review the current stage before following up.`}
        </Notice>
      )}
      <div className="monitoring-follow-up">
        <h3>Next follow-up</h3>
        <p>
          {plan?.next_check ||
            "Follow-up will be available after CLEAR prepares a recovery plan."}
        </p>
        <p className="panel-footnote">
          New logistics events trigger a reassessment. These records do not
          confirm delivery or customs release.
        </p>
      </div>
      <section
        className="monitoring-section"
        aria-labelledby="shipment-monitor-heading"
      >
        <h3 id="shipment-monitor-heading">Shipment arrival</h3>
        <dl className="monitoring-facts">
          <div>
            <dt>Shipment</dt>
            <dd>{item.shipment_id}</dd>
          </div>
          <div>
            <dt>Latest recorded ETA</dt>
            <dd>{date(item.shipment.eta)}</dd>
          </div>
          <div>
            <dt>Arrival port</dt>
            <dd>{item.shipment.port_of_discharge}</dd>
          </div>
          {item.shipment.vessel && (
            <div>
              <dt>Vessel</dt>
              <dd>{item.shipment.vessel}</dd>
            </div>
          )}
        </dl>
      </section>
      <section
        className="monitoring-section"
        aria-labelledby="transfer-monitor-heading"
      >
        <h3 id="transfer-monitor-heading">Transfer follow-up</h3>
        {executed.length ? (
          executed.map((action) => (
            <div className="monitoring-transfer" key={action.validation_id}>
              <p className="monitoring-order">
                <CheckCircle2 size={16} />
                Order created:{" "}
                {action.sto?.purchase_order || "See agent activity"}
              </p>
              <dl className="monitoring-facts">
                <div>
                  <dt>Route</dt>
                  <dd>
                    Plant {action.validation.source_plant}{" "}
                    <ArrowRight size={14} aria-label="to" /> Plant{" "}
                    {action.validation.destination_plant}
                  </dd>
                </div>
                <div>
                  <dt>Quantity</dt>
                  <dd>
                    {number(
                      action.sto?.quantity_t ?? action.validation.quantity,
                    )}{" "}
                    t
                  </dd>
                </div>
                {action.approval && (
                  <div>
                    <dt>Approved by</dt>
                    <dd>{action.approval.approver}</dd>
                  </div>
                )}
              </dl>
              <p className="panel-footnote">
                Confirm delivery and goods receipt with the receiving plant.
              </p>
            </div>
          ))
        ) : (
          <p>
            {item.status === "monitoring" && plan && !plan.actions.length
              ? "No stock transfer required by the current plan. Follow the shipment and next follow-up above."
              : "No stock transport order has been created in the current plan."}
          </p>
        )}
      </section>
      <section
        className="monitoring-section"
        aria-labelledby="stock-monitor-heading"
      >
        <h3 id="stock-monitor-heading">
          Stock position · {item.inventory.material}
        </h3>
        <p className="panel-footnote">
          In-transit stock is separate from available stock until goods receipt.
        </p>
        <div className="table-scroll">
          <table
            className="monitoring-stock"
            aria-labelledby="stock-monitor-heading"
          >
            <thead>
              <tr>
                <th scope="col">Plant</th>
                <th scope="col">Available</th>
                <th scope="col">In transit</th>
                <th scope="col">Safety stock</th>
              </tr>
            </thead>
            <tbody>
              {item.inventory.plants.map((plant) => (
                <tr key={plant.plant}>
                  <th scope="row">{plant.plant}</th>
                  <td>{number(plant.unrestricted_t)} t</td>
                  <td>{number(plant.in_transit_t)} t</td>
                  <td>{number(plant.safety_stock_t)} t</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="panel-footnote">
          Source: S/4HANA (mock). Case updated {date(item.updated_at)}.
        </p>
      </section>
    </div>
  );
}

function Overview({ item }: { item: Case }) {
  const plan = item.plan;
  if (!plan)
    return (
      <div className="analysis-state">
        <span className="analysis-icon">
          {item.running ? (
            <ClearMark active size={84} />
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
        {item.running && (
          <div className="analysis-skeleton" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        )}
      </div>
    );
  const impact = plan.impact;
  const transfer = plan.actions.find(
    (action) => action.validation.valid,
  )?.validation;
  return (
    <>
      <div className="recommendation">
        <GitBranch size={20} />
        <div>
          <h3>Recommended next move</h3>
          {transfer && (
            <p className="recommendation-route">
              Transfer <strong>{number(transfer.quantity)} t</strong>
              <span>
                Plant {transfer.source_plant} <ArrowRight size={14} /> Plant{" "}
                {transfer.destination_plant}
              </span>
            </p>
          )}
          <p>{plan.recommendation}</p>
        </div>
      </div>
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
      <div className="panel-heading">
        <h3>Exception brief</h3>
        <span className="source-label">{item.shipment_id}</span>
      </div>
      <p className="exception-title">{plan.exception}</p>
      {impact.prediction.basis.fallback_reason && (
        <Notice tone="warning" title="Backup estimate in use">
          SAP-RPT is unavailable. The estimate uses the historical median;
          review the prediction source before deciding.
        </Notice>
      )}
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
  const reconciliation = item.reconciliation;
  const quantityIssue = reconciliation?.discrepancies.find(
    (d) => d.field === "quantity",
  );
  const reference = reconciliation?.purchase_order;
  return (
    <>
      <div className="panel-heading">
        <FileText size={20} />
        <div>
          <h3>Shipping evidence</h3>
          <p>Supplier documents compared with the S/4HANA purchase order.</p>
        </div>
      </div>
      {quantityIssue && (
        <Notice tone="warning" title="Quantity mismatch found">
          The purchase order expects{" "}
          {number(Number(quantityIssue.purchase_order_value))} t.{" "}
          {quantityIssue.mismatched_documents
            .map(
              (doc) =>
                `${documentTitles[doc] || doc}: ${number(Number(quantityIssue.document_values[doc]))} t`,
            )
            .join("; ")}
          . Review the highlighted source lines below.
        </Notice>
      )}
      {reference && (
        <div className="reconciliation-summary">
          <div className="subsection-heading">
            <h4>Quantity comparison</h4>
            <span>Verified source values</span>
          </div>
          <div
            className="quantity-comparison"
            role="list"
            aria-label="Quantity comparison"
          >
            <div role="listitem" className="quantity-source reference">
              <span>Purchase order</span>
              <strong>
                {number(reference.quantity)} <small>t</small>
              </strong>
              <span>PO {reference.purchase_order}</span>
              <span className="comparison-result">
                <ShieldCheck size={13} />
                ERP reference
              </span>
            </div>
            {item.documents.required_documents
              .filter(
                (type) =>
                  type === "commercial_invoice" || type === "packing_list",
              )
              .map((type) => {
                const extraction = reconciliation.verified_extractions.find(
                  (e) => e.document_type === type && e.field === "quantity",
                );
                const mismatch =
                  quantityIssue?.mismatched_documents.includes(type);
                return (
                  <div
                    role="listitem"
                    key={type}
                    className={`quantity-source ${mismatch ? "mismatch" : ""}`}
                  >
                    <span>{documentTitles[type]}</span>
                    <strong>
                      {extraction ? (
                        <>
                          {number(Number(extraction.value))} <small>t</small>
                        </>
                      ) : (
                        "Not verified"
                      )}
                    </strong>
                    <span>Supplier document</span>
                    <span className="comparison-result">
                      {extraction ? (
                        mismatch ? (
                          <>
                            <TriangleAlert size={13} />
                            Does not match
                          </>
                        ) : (
                          <>
                            <CheckCircle2 size={13} />
                            Matches PO
                          </>
                        )
                      ) : (
                        <>
                          <Info size={13} />
                          Review source
                        </>
                      )}
                    </span>
                  </div>
                );
              })}
          </div>
          <p className="panel-footnote">
            Quantities are normalized to tonnes. Package counts and gross
            weights are not treated as a stated goods quantity.
          </p>
        </div>
      )}
      <div className="subsection-heading">
        <h4>Source documents</h4>
        <span>
          {item.documents.documents.length} of{" "}
          {item.documents.required_documents.length} available
        </span>
      </div>
      {item.documents.required_documents.map((type) => {
        const doc = item.documents.documents.find(
          (d) => d.document_type === type,
        );
        const findings =
          reconciliation?.discrepancies.filter((d) =>
            d.mismatched_documents.includes(type),
          ) || [];
        const compared = Boolean(
          reconciliation?.verified_extractions.some(
            (e) => e.document_type === type && quantityIssue?.field === e.field,
          ),
        );
        return (
          <details
            className="document"
            key={type}
            open={findings.length > 0 || compared}
          >
            <summary>
              <span>
                <FileText size={17} />
                {documentTitles[type] || type}
              </span>
              <span
                className={`document-badge ${!doc || findings.length ? "warning" : ""}`}
              >
                {findings.length ? (
                  <TriangleAlert size={13} />
                ) : doc && reconciliation ? (
                  <CheckCircle2 size={13} />
                ) : (
                  <FileText size={13} />
                )}
                {!doc
                  ? "Missing"
                  : findings.length
                    ? "Discrepancy"
                    : reconciliation
                      ? "Reviewed"
                      : "Available"}
                <ChevronRight size={14} />
              </span>
            </summary>
            {doc ? (
              <pre>
                {doc.text.split("\n").map((line, i) => {
                  const extraction = reconciliation?.verified_extractions.find(
                    (e) =>
                      e.document_type === type &&
                      e.quote.trim() === line.trim() &&
                      reconciliation.discrepancies.some(
                        (f) => f.field === e.field,
                      ),
                  );
                  return (
                    <span
                      key={i}
                      className={
                        extraction
                          ? findings.some((f) => f.field === extraction.field)
                            ? "doc-mismatch"
                            : "doc-match"
                          : ""
                      }
                    >
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
                <span>
                  {findings
                    .map(
                      (f) =>
                        `${f.field === "quantity" ? "Quantity" : f.field}: ${f.document_values[type]}${f.field === "quantity" ? " t" : ""} in this document vs ${f.purchase_order_value}${f.field === "quantity" ? " t" : ""} in the purchase order`,
                    )
                    .join(". ")}
                </span>
              </div>
            )}
          </details>
        );
      })}
      {!reconciliation && (
        <Notice title="Evidence check pending">
          Documents are available to read. CLEAR has not reconciled them for
          this case yet.
        </Notice>
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
                plant.unrestricted_t <= plant.safety_stock_t
                  ? "short"
                  : "covered"
              }
            >
              {plant.unrestricted_t < plant.safety_stock_t
                ? "Below safety stock"
                : plant.unrestricted_t === plant.safety_stock_t
                  ? "At safety stock · no spare stock"
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
              <caption className="sr-only">
                Daily material demand at plant {plant.plant}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Order</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Use / day</th>
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
  error,
  onDecision,
}: {
  action: Action;
  caseItem: Case;
  disabled: boolean;
  approver: string;
  error: string;
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
        <Notice tone="warning" title="Transfer rejected">
          Rejected by {action.approval.approver}. A planner needs to decide the
          next step.
        </Notice>
      ) : !isPending ? (
        <div className="panel-empty">
          This plan is not currently accepting a decision.
        </div>
      ) : (
        <>
          <Notice
            tone="warning"
            title="Approval creates a stock transport order"
          >
            Approve to transfer {number(valid.quantity)} t from plant{" "}
            {valid.source_plant} to plant {valid.destination_plant}. Your
            decision is recorded as {approver}.
          </Notice>
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
          {!reason.trim() && (
            <p className="decision-help">
              To reject this transfer, add a reason above. A note is optional
              when approving.
            </p>
          )}
          {error && (
            <div className="notice notice-error decision-error">
              <TriangleAlert size={18} />
              <div>
                <strong>Decision not recorded</strong>
                <p>
                  The request failed. Review the current case before trying
                  again.
                </p>
                <details className="error-details">
                  <summary>Request details</summary>
                  {error}
                </details>
              </div>
            </div>
          )}
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
  const hasRunLive = useRef(running);
  const [showNotes, setShowNotes] = useState(false);
  const [following, setFollowing] = useState(true);
  const visibleEntries = showNotes
    ? entries
    : entries.filter(
        (entry) => entry.kind !== "note" && entry.kind !== "delegation",
      );
  useEffect(() => {
    if (running) hasRunLive.current = true;
    if (follow.current && scroll.current && hasRunLive.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [entries.length, running]);
  return (
    <aside className="timeline-panel">
      <div className="timeline-heading">
        <h3>
          <Activity size={17} />
          Agent activity
        </h3>
        <span className={running ? "activity-live" : "source-label"}>
          {running ? "Live" : `${visibleEntries.length} key steps`}
        </span>
      </div>
      <p className="timeline-caption">
        Evidence, checks, and decisions as they happen.
      </p>
      <label className="timeline-filter">
        <input
          type="checkbox"
          checked={showNotes}
          onChange={(e) => setShowNotes(e.target.checked)}
        />
        Include agent notes
      </label>
      <div
        className="timeline-scroll"
        ref={scroll}
        onScroll={(e) => {
          const element = e.currentTarget;
          follow.current =
            element.scrollHeight - element.scrollTop - element.clientHeight <
            100;
          setFollowing(follow.current);
        }}
        role="log"
        aria-label="Agent activity timeline"
        aria-relevant="additions"
        aria-live="off"
      >
        {visibleEntries.map((entry) => (
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
            {entry.kind === "note" || entry.kind === "delegation" ? (
              <details className="agent-note">
                <summary>
                  {entry.kind === "delegation"
                    ? "Delegation details"
                    : "Agent explanation"}
                </summary>
                <p>{entry.summary}</p>
              </details>
            ) : (
              <p>{entry.summary}</p>
            )}
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
            <ClearMark active size={22} />
            Agents are working…
          </div>
        )}
      </div>
      {!following && (
        <button
          className="jump-latest"
          onClick={() => {
            if (scroll.current)
              scroll.current.scrollTop = scroll.current.scrollHeight;
            follow.current = true;
            setFollowing(true);
          }}
        >
          Jump to latest activity <ChevronDown size={14} />
        </button>
      )}
      <div className="timeline-bottom">
        <ShieldCheck size={13} />
        Tool results and decisions are recorded.
      </div>
    </aside>
  );
}
