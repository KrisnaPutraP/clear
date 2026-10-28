"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowRight,
  ChevronDown,
  Info,
  Menu,
  RefreshCw,
  TriangleAlert,
  X,
} from "lucide-react";
import { api } from "../../lib/api";
import type {
  Action,
  Assessment,
  Case,
  Resolution,
  CaseStatus,
  CaseSummary,
  Event,
  Health,
  LogEntry,
} from "../../lib/types";
import { Harbour } from "../harbour";
import { Sky } from "../sky";

const statuses: Record<CaseStatus, string> = {
  analyzing: "Analyzing",
  awaiting_approval: "Awaiting approval",
  executing: "Executing",
  monitoring: "Monitoring",
  needs_human_decision: "Needs a decision",
};
const statusDescriptions: Record<CaseStatus, string> = {
  analyzing:
    "CLEAR is investigating. You can read the evidence while the agents work.",
  awaiting_approval:
    "Your approval is needed before CLEAR can create this transfer.",
  executing:
    "Approval received. CLEAR is creating the order and checking stock.",
  monitoring:
    "No decision is pending. Open monitoring to review the latest records and follow-up.",
  needs_human_decision:
    "A planner needs to decide the next step. Review the recommendation below.",
};
// The case banner already names the state; this line says what it asks of you.
const nextStepTitles: Record<CaseStatus, string> = {
  analyzing: "CLEAR is working on this case",
  awaiting_approval: "One decision is waiting for you",
  executing: "Putting your approved plan into action",
  monitoring: "Nothing needs you right now",
  needs_human_decision: "This case needs a planner’s call",
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
  purchase_order: "Purchase order",
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
  return (
    <div
      className={`notice notice-${tone}`}
      role={tone === "error" ? "alert" : "status"}
    >
      <span className="notice-mark" aria-hidden="true" />
      <div className="notice-copy">
        <strong>{title}</strong>
        <div>{children}</div>
      </div>
      {onDismiss && (
        <button onClick={onDismiss} aria-label="Dismiss notification">
          <X size={16} />
        </button>
      )}
    </div>
  );
}

function Status({ status }: { status: CaseStatus }) {
  return (
    <span className={`status ${status}`}>{statuses[status] || status}</span>
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
  // The landing page hands over one demo event (?event=…): the simulator
  // opens with it marked, and the planner still sends it themselves.
  const [suggested, setSuggested] = useState("");
  const keepSimulatorOpen = useRef(false);
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("event");
    if (!id) return;
    keepSimulatorOpen.current = true;
    setSuggested(id);
    setEventsExpanded(true);
    requestAnimationFrame(() =>
      document
        .getElementById("event-simulator")
        ?.scrollIntoView({ block: "start" }),
    );
  }, []);
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

  function closeNavigation() {
    setNavigationOpen(false);
    navigationButton.current?.focus();
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
      if (event.key === "Escape") closeNavigation();
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
          if (!keepSimulatorOpen.current) setEventsExpanded(false);
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
  // While another case loads, the previous one stays on screen, dimmed and
  // inert, so the harbour scene is never torn down: it sails on to the new
  // case's state, and the panels fade across.
  const switching = !activeCase && Boolean(selectedId) && Boolean(detail);
  const shownCase = activeCase || (switching ? detail : null);
  const busy =
    pending || Boolean(health?.running) || Boolean(activeCase?.running);
  const disabled = busy || !health || Boolean(error) || switching;
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
      setSuggested("");
      keepSimulatorOpen.current = false;
      setFeedback({
        title: "Event received",
        message: `${eventTitles[event.event_id] || "Logistics event"} was sent to ${result.case_id}.`,
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
            ? `Recorded as ${approver}. CLEAR is creating the order and checking stock.`
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

  async function resolveCase(option: string | null, note: string) {
    if (!activeCase || mutationLock.current) return;
    mutationLock.current = true;
    setPending(true);
    setActionError("");
    setFeedback(null);
    try {
      await api(`/cases/${encodeURIComponent(activeCase.case_id)}/resolution`, {
        method: "POST",
        body: JSON.stringify({ approver, option, note: note.trim() || null }),
      });
      setTab("Overview");
      setFeedback({
        title: "Decision recorded",
        message: `Recorded as ${approver}. CLEAR keeps monitoring the case; carry out the chosen course in your own systems.`,
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
      data-expanded={eventsExpanded}
    >
      <button
        className="event-toggle"
        aria-expanded={eventsExpanded}
        aria-controls="event-options"
        onClick={() => setEventsExpanded(!eventsExpanded)}
      >
        <span className="event-toggle-copy">
          <h2 id="event-heading">Demo event simulator</h2>
          <span>
            {eventsExpanded
              ? "Send a simulated logistics event to start or reassess a case."
              : "Start another case or send an ETA update."}
          </span>
        </span>
        <ChevronDown size={18} aria-hidden="true" />
      </button>
      <div className="event-grid" id="event-options" hidden={!eventsExpanded}>
        {events.map((event) => {
          const etaNeedsCase =
            event.type === "eta_change" &&
            !cases.some((c) => c.shipment_id === event.shipment_id);
          const scenario =
            event.scenario.replace(/\D/g, "") === "2" ? "2" : "1";
          return (
            <button
              className={`event-card ${suggested === event.event_id ? "suggested" : ""}`}
              key={event.event_id}
              disabled={disabled || etaNeedsCase}
              onClick={() => void sendEvent(event)}
              title={
                etaNeedsCase
                  ? "Start the customs document hold case first."
                  : event.description
              }
            >
              <span className="event-copy">
                <span className="event-meta">
                  {event.scenario} ·{" "}
                  {event.type === "eta_change" ? "Follow-up" : "New exception"}{" "}
                  · {event.shipment_id}
                </span>
                <h3>
                  {eventTitles[event.event_id] ||
                    event.type.replaceAll("_", " ")}
                </h3>
                <span className="event-description">{event.description}</span>
              </span>
              <span className="event-go">
                {etaNeedsCase
                  ? "Start the document case first"
                  : busy
                    ? "Wait for the current run"
                    : event.type === "eta_change"
                      ? "Reassess case"
                      : "Start investigation"}
                <ArrowRight size={15} aria-hidden="true" />
              </span>
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
      <Sky />
      <a className="skip-link" href="#workspace">
        Skip to case workspace
      </a>
      {navigationOpen && (
        <button
          className="navigation-backdrop"
          aria-label="Close navigation"
          tabIndex={-1}
          onClick={closeNavigation}
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
          onClick={closeNavigation}
          aria-label="Close navigation"
        >
          <X size={20} />
        </button>
        <a className="brand" href="/" aria-label="CLEAR home">
          <ClearMark size={30} />
          <span className="brand-name">CLEAR</span>
        </a>
        <p className="brand-line">Shipment exception desk</p>

        <div className="sidebar-heading">
          <h2>Cases</h2>
          <span>{loading ? "…" : cases.length}</span>
        </div>
        <nav className="case-list" aria-label="Cases">
          {cases.map((item) => (
            <button
              key={item.case_id}
              className={`case-link ${item.status} ${selectedId === item.case_id ? "selected" : ""}`}
              aria-current={selectedId === item.case_id ? "page" : undefined}
              onClick={() => {
                setSelectedId(item.case_id);
                setTab("Overview");
                setActionError("");
                setFeedback(null);
                if (navigationOpen) closeNavigation();
              }}
            >
              <span className="case-mark" aria-hidden="true" />
              <span className="case-link-copy">
                <span className="case-link-id">{item.case_id}</span>
                <span className="case-link-meta">
                  {item.shipment_id} · <Status status={item.status} />
                </span>
              </span>
            </button>
          ))}
          {!cases.length && (
            <p className="sidebar-empty">
              Cases appear here when a logistics event arrives.
            </p>
          )}
        </nav>

        <div className="sidebar-bottom">
          <p className="guardrail">
            <strong>Human in control.</strong> Every ERP write needs a named
            planner’s approval.
          </p>
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
            <ClearMark size={24} />
          </a>
          <h1>Exception workspace</h1>
          <div className="topbar-status">
            {busy && (
              <span className="live-indicator">
                <ClearMark active size={20} />
                <span className="connection-label">Agents working</span>
              </span>
            )}
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
                <span className="attention-count">{attention.length}</span>
                <span className="attention-label">needs attention</span>
              </button>
            )}
            <div className="connection" role="status">
              <span
                className={`connection-dot ${error ? "offline" : health ? "online" : ""}`}
              />
              <span className="connection-label">
                {error
                  ? "Connection interrupted"
                  : health
                    ? "API connected"
                    : "Connecting…"}
              </span>
            </div>
          </div>
        </header>
        <main inert={navigationOpen || undefined}>
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
              <button
                className="inline-button"
                onClick={() => setRefreshKey((k) => k + 1)}
              >
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

          {/* Until the first answer arrives, or while a case opens, the
              harbour holds the screen alone; the simulator leads only when
              there is no case at all. */}
          {!shownCase && !loading && !selectedId && eventSimulator}

          <div id="workspace" tabIndex={-1} className="workspace-anchor">
            <h2 className="sr-only">Case workspace</h2>
          </div>

          {!shownCase ? (
            <section className="empty-workspace scene">
              <div className="scene-stage">
                <Harbour item={null} running={Boolean(selectedId) || loading} />
                <div className="scene-copy">
                  <h2>
                    {selectedId
                      ? "Opening your case…"
                      : loading
                        ? "Opening the workspace…"
                        : "Your next move starts here."}
                  </h2>
                  <p>
                    {selectedId
                      ? "Gathering the latest evidence, plan, and agent activity."
                      : loading
                        ? "Gathering the cases and their agent activity."
                        : "The harbour is quiet. Send a logistics event and CLEAR investigates the evidence, sizes the impact, and brings you one validated decision."}
                  </p>
                </div>
              </div>
            </section>
          ) : (
            <div className={`case-grid ${switching ? "switching" : ""}`}>
              <section className="case-banner scene" aria-label="Case">
                <div className="scene-stage">
                  <Harbour item={shownCase} running={shownCase.running} />
                  <div className="scene-copy case-in" key={shownCase.case_id}>
                    <h2>
                      <Status status={shownCase.status} />
                    </h2>
                  </div>
                </div>
                <dl className="case-voyage case-in" key={shownCase.case_id}>
                  <div>
                    <dt>Case</dt>
                    <dd>
                      {shownCase.case_id} · {shownCase.shipment_id}
                    </dd>
                  </div>
                  <div>
                    <dt>Voyage</dt>
                    <dd>
                      {shownCase.shipment.port_of_loading}
                      <ArrowRight size={14} aria-label="to" />
                      {shownCase.shipment.port_of_discharge}
                    </dd>
                  </div>
                  {shownCase.shipment.vessel && (
                    <div>
                      <dt>Vessel</dt>
                      <dd>{shownCase.shipment.vessel}</dd>
                    </div>
                  )}
                  <div>
                    <dt>ETA</dt>
                    <dd>{date(shownCase.shipment.eta)}</dd>
                  </div>
                </dl>
              </section>
              <CaseProgress
                key={`progress-${shownCase.case_id}`}
                item={shownCase}
                entries={logs}
                onNavigate={openCaseTab}
              />
                <section
                  className="detail-panel case-in"
                  key={`detail-${shownCase.case_id}`}
                >
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
                          (shownCase.status === "awaiting_approval" ||
                            shownCase.status === "needs_human_decision") && (
                            <span className="tab-count" aria-label="1 pending">
                              1
                            </span>
                          )}
                        {name === "Documents" &&
                          Boolean(
                            shownCase.reconciliation?.discrepancies.length,
                          ) && (
                            <span
                              className="tab-alert"
                              aria-label="Discrepancy found"
                            />
                          )}
                      </button>
                    ))}
                  </div>
                  <div
                    className="panel-content"
                    key={`${shownCase.case_id}-${tab}`}
                    role="tabpanel"
                    tabIndex={0}
                    id="case-tabpanel"
                    aria-labelledby={`tab-${tab}`}
                  >
                    {tab === "Overview" && <Overview item={shownCase} />}
                    {tab === "Documents" && <Documents item={shownCase} />}
                    {tab === "Inventory" && <Inventory item={shownCase} />}
                    {tab === "Monitoring" && <Monitoring item={shownCase} />}
                    {tab === "Approval" && (
                      <div className="approval-list">
                        {shownCase.status === "needs_human_decision" && (
                          <Resolve
                            caseItem={shownCase}
                            disabled={disabled}
                            approver={approver}
                            error={actionError}
                            onResolve={resolveCase}
                          />
                        )}
                        {shownCase.status === "needs_human_decision" &&
                        !shownCase.plan?.actions.length ? null : !shownCase
                            .plan?.actions.length ? (
                          <div className="panel-empty">
                            <h3>No transfer to approve</h3>
                            <p>
                              No transfer is awaiting approval. Check the
                              overview for monitoring instructions or a decision
                              that needs your attention.
                            </p>
                          </div>
                        ) : (
                          shownCase.plan.actions.map((action) => (
                            <Approval
                              key={action.validation_id}
                              action={action}
                              caseItem={shownCase}
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
                <div className="case-rail case-in" key={`rail-${shownCase.case_id}`}>
                  <Timeline
                    entries={logs}
                    running={shownCase.running}
                  />
                  {shownCase.plan && (
                    <section
                      className="case-evidence"
                      aria-labelledby="evidence-heading"
                    >
                      <div className="rail-heading">
                        <h3 id="evidence-heading">Evidence</h3>
                        <span>{shownCase.plan.evidence.length} findings</span>
                      </div>
                      <ul className="evidence-list">
                        {shownCase.plan.evidence.map((evidence, i) => (
                          <li key={i}>
                            <p>
                              <Typed
                                text={evidence.fact}
                                version={runVersion(shownCase)}
                                delay={120 + i * 90}
                              />
                            </p>
                            <span>{evidence.source}</span>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {shownCase.plan && (
                    <section className="next-check">
                      <h3>What happens next</h3>
                      <FollowUp
                        text={shownCase.plan.next_check}
                        version={runVersion(shownCase)}
                        compact
                      />
                      <button
                        className="text-button"
                        onClick={() => openCaseTab("Monitoring")}
                      >
                        View monitoring <ArrowRight size={14} />
                      </button>
                    </section>
                  )}
                </div>
            </div>
          )}

          {shownCase && eventSimulator}

          <footer>
            <span>Evidence-backed plans. Human-approved actions.</span>
            <span>
              Synthetic demo data · {health?.model || "CLEAR"} · {awaiting}{" "}
              awaiting approval
            </span>
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
  const steps = [
    "Investigate",
    "Assess impact",
    item.status === "needs_human_decision" || item.resolution
      ? "Planner decision"
      : item.status === "monitoring" && !item.plan?.actions.length
        ? "No action needed"
        : "Review & approve",
    "Monitor",
  ];
  const destinations: Tab[] = [
    "Documents",
    "Overview",
    item.status === "needs_human_decision"
      ? "Approval"
      : !item.plan?.actions.length
        ? "Overview"
        : "Approval",
    "Monitoring",
  ];
  return (
    <section
      className={`case-progress case-in ${item.status} ${active ? "running" : ""}`}
      aria-label="Case progress"
    >
      <div className="case-next-step" role="status" aria-atomic="true">
        <span className="case-state-icon">
          {active && <ClearMark active size={36} />}
        </span>
        <div className="case-next-copy">
          <h2>
            {active
              ? item.status === "executing"
                ? "Putting your approved plan into action"
                : "CLEAR is working on this case"
              : nextStepTitles[item.status]}
          </h2>
          <p>
            <Typed
              text={item.status_reason || statusDescriptions[item.status]}
              version={runVersion(item)}
            />
          </p>
          {active && (
            <p className="run-update">
              <strong>{latest?.actor || "Orchestrator"}</strong>
              {latest
                ? ` · ${latest.summary}`
                : " · Starting the investigation. Results appear as each tool finishes."}
            </p>
          )}
          {active && item.plan && (
            <p className="updating-plan">
              <Info size={14} />
              The plan below is from the previous run. CLEAR is reassessing it;
              decisions are paused.
            </p>
          )}
        </div>
        {item.status === "awaiting_approval" && !active && (
          <button
            className="primary-button decision"
            onClick={() => onNavigate("Approval")}
          >
            Review transfer <ArrowRight size={16} />
          </button>
        )}
        {item.status === "needs_human_decision" && !active && (
          <button
            className="primary-button decision"
            onClick={() => onNavigate("Approval")}
          >
            Make the call <ArrowRight size={16} />
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
            <span className="step-mark" aria-hidden="true" />
            <button onClick={() => onNavigate(destinations[i])}>{step}</button>
            {i < steps.length - 1 && (
              <span className="step-line" aria-hidden="true" />
            )}
          </li>
        ))}
      </ol>
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
      {item.resolution && <ResolutionNote resolution={item.resolution} />}
      <div className="monitoring-follow-up">
        <h3>Next follow-up</h3>
        {plan?.next_check ? (
          <FollowUp text={plan.next_check} version={runVersion(item)} />
        ) : (
          <p>Follow-up will be available after CLEAR prepares a recovery plan.</p>
        )}
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
            <ClearMark active size={96} />
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
            ? "The agents are reading the documents, checking stock, and sizing the impact. Follow each step in the signal log."
            : "Review the case status and the signal log for the reason."}
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
        <h3 className="recommendation-move">
          {transfer ? (
            <>
              Transfer <strong>{number(transfer.quantity)} t</strong>
            </>
          ) : item.resolution ? (
            "Planner’s call recorded"
          ) : plan.escalation ? (
            "Escalate to a planner"
          ) : (
            "Keep the current plan"
          )}
        </h3>
        {transfer && (
          <p className="move-route">
            Plant {transfer.source_plant}
            <ArrowRight size={22} aria-label="to" />
            Plant {transfer.destination_plant}
          </p>
        )}
        <p>
          <Typed text={plan.recommendation} version={runVersion(item)} />
        </p>
      </div>
      <dl className="figures">
        <Figure
          label="Resolution estimate"
          value={number(impact.prediction.predicted_days)}
          unit="days"
          note={impact.prediction.source}
        />
        <Figure
          label="Stock coverage"
          value={number(impact.coverage_days)}
          unit="days"
          note={`${number(impact.required_coverage_days)} days required`}
        />
        <Figure
          label="Shortage before recovery"
          value={number(impact.shortage_t)}
          unit="t"
          note={impact.covered ? "Covered" : "Not covered"}
          warning={!impact.covered}
        />
      </dl>
      {impact.prediction.basis.fallback_reason && (
        <Notice tone="warning" title="Backup estimate in use">
          SAP-RPT is unavailable. The estimate uses the historical median;
          review the prediction source before deciding.
        </Notice>
      )}
      {item.resolution ? (
        <ResolutionNote resolution={item.resolution} />
      ) : plan.escalation && (
        <div className="escalation" role="note">
          <div>
            <strong>A decision needs your attention</strong>
            <p>
              <Typed
                text={plan.escalation}
                version={runVersion(item)}
                delay={200}
              />
            </p>
          </div>
        </div>
      )}
      <section className="brief" aria-labelledby="brief-heading">
        <h4 id="brief-heading">What happened</h4>
        <p className="exception-title">
          <Typed text={plan.exception} version={runVersion(item)} delay={300} />
        </p>
      </section>
      <section aria-labelledby="options-heading">
        <div className="subsection-heading">
          <h4 id="options-heading">Recovery options</h4>
          <span>Calculated by tools, checked by the validator</span>
        </div>
        <div className="options">
          <Option name="Current plan" assessment={impact} recommended={false} />
          {plan.options.map((option) => (
            <Option
              key={option.name}
              name={option.name}
              assessment={option.assessment}
              recommended={option.name === plan.recommended_option}
              chosen={option.name === item.resolution?.option}
              note={option.note}
              version={runVersion(item)}
              valid={option.validation?.valid}
            />
          ))}
        </div>
      </section>
    </>
  );
}

// Agent-written text types itself in when a run's result first appears,
// fast enough that a long paragraph still lands within about a second. The
// untyped rest is laid out but transparent, so nothing reflows and a screen
// reader reads the whole text. version is the case's updated_at: the same
// text from the same run, on another tab or after switching back to the case,
// appears at once; a new run types it again.
const typedBefore = new Set<string>();
// While a run is in progress the text on screen is the previous result, so
// it shows as it is; only a finished run's text types in.
const runVersion = (item: Case) => (item.running ? null : item.updated_at);
function Typed({
  text,
  version = "",
  delay = 0,
}: {
  text: string;
  version?: string | null;
  delay?: number;
}) {
  const id = `${version}\u0000${text}`;
  if (version === null) typedBefore.add(id);
  const [state, setState] = useState(() => ({
    id,
    count: typedBefore.has(id) ? text.length : 0,
  }));
  const current =
    state.id === id
      ? state
      : { id, count: typedBefore.has(id) ? text.length : 0 };
  if (current !== state) setState(current);
  useEffect(() => {
    if (typedBefore.has(id)) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      typedBefore.add(id);
      setState({ id, count: text.length });
      return;
    }
    const duration = Math.min(1100, Math.max(250, text.length * 9));
    let frame = 0;
    let start = 0;
    const step = (now: number) => {
      start ||= now + delay;
      const progress = Math.max(0, now - start) / duration;
      const count = Math.min(text.length, Math.ceil(progress * text.length));
      setState({ id, count });
      if (count < text.length) frame = requestAnimationFrame(step);
      else typedBefore.add(id);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [id, text, delay]);
  const count = current.count;
  if (count >= text.length) return <>{text}</>;
  return (
    <span className="typed">
      {text.slice(0, count)}
      <span className="typed-rest">{text.slice(count)}</span>
    </span>
  );
}

// An agent often writes its follow-up as one paragraph of numbered points,
// "1. CUSTOMS HOLD (binding constraint): … 2. …". Split it on the numbers
// only when they count up from 1, so a figure such as "4.83" or a sentence
// ending in a number never breaks it, and lift an upper-case lead-in before
// a colon out as the point's label.
type FollowUpPoint = { label: string | null; text: string };
function followUpPoints(text: string): FollowUpPoint[] | null {
  const marks: { at: number; end: number }[] = [];
  for (const match of text.matchAll(/(^|\s)(\d{1,2})\.\s+/g)) {
    if (Number(match[2]) !== marks.length + 1) continue;
    const at = match.index + match[1].length;
    marks.push({ at, end: match.index + match[0].length });
  }
  if (marks.length < 2 || text.slice(0, marks[0].at).trim()) return null;
  return marks.map((mark, i) => {
    const point = text.slice(mark.end, marks[i + 1]?.at ?? text.length).trim();
    const lead = point.match(/^([^:a-z]{3,60}?)(?:\s*\(([^)]*)\))?:\s+([\s\S]*)$/);
    if (!lead || !/[A-Z]{2}/.test(lead[1])) return { label: null, text: point };
    const label = lead[1].trim() + (lead[2] ? ` · ${lead[2]}` : "");
    return { label, text: lead[3] };
  });
}

function FollowUp({
  text,
  version,
  compact = false,
}: {
  text: string;
  version: string | null;
  compact?: boolean;
}) {
  const points = followUpPoints(text);
  if (!points)
    return (
      <p className={`follow-up-text ${compact ? "clamped" : ""}`}>
        <Typed text={text} version={version} delay={300} />
      </p>
    );
  // The rail lists what to watch; the Monitoring tab carries the detail.
  if (compact && points.every((point) => point.label))
    return (
      <ol className="follow-up compact">
        {points.map((point, i) => (
          <li key={i}>
            <Typed text={point.label!} version={version} delay={300 + i * 80} />
          </li>
        ))}
      </ol>
    );
  return (
    <ol className={`follow-up ${compact ? "compact" : ""}`}>
      {points.map((point, i) => (
        <li key={i}>
          {point.label && <strong>{point.label}</strong>}
          <span className={compact ? "clamped" : ""}>
            <Typed text={point.text} version={version} delay={300 + i * 80} />
          </span>
        </li>
      ))}
    </ol>
  );
}

function Figure({
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
      <dt>{label}</dt>
      <dd>
        <strong>
          {value}
          <small>{unit}</small>
        </strong>
        <span>{note}</span>
      </dd>
    </div>
  );
}

function Option({
  name,
  assessment,
  recommended,
  chosen = false,
  note,
  version,
  valid,
}: {
  name: string;
  assessment: Assessment;
  recommended: boolean;
  chosen?: boolean;
  note?: string;
  version?: string | null;
  valid?: boolean;
}) {
  const coverage =
    assessment.required_coverage_days > 0
      ? Math.min(
          100,
          Math.max(
            0,
            (assessment.coverage_days / assessment.required_coverage_days) *
              100,
          ),
        )
      : 100;
  return (
    <div
      className={`option ${recommended ? "recommended" : ""} ${valid === false ? "rejected" : ""}`}
    >
      <div className="option-title">
        <strong>{name}</strong>
        {recommended && <span className="option-mark">Recommended</span>}
        {chosen && <span className="option-mark chosen">Chosen</span>}
        {valid === false && (
          <span className="validation-rejected">
            Rejected by validator
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
      <div
        className="coverage-bar"
        role="img"
        aria-label={`${number(assessment.coverage_days)} of ${number(assessment.required_coverage_days)} days covered`}
      >
        <span style={{ width: `${coverage}%` }} />
      </div>
      <div className="coverage-caption">
        <span>{number(assessment.coverage_days)} days coverage</span>
        <span>{number(assessment.required_coverage_days)} required</span>
      </div>
      {assessment.transfer && (
        <p className="option-note">
          Transfer cost ${number(assessment.transfer.cost_usd)} · lead time{" "}
          {number(assessment.transfer.lead_time_days)} days
        </p>
      )}
      {assessment.deferred_orders.length > 0 && (
        <p className="option-note">
          Deferred:{" "}
          {assessment.deferred_orders.map((o) => o.order_id).join(", ")}
        </p>
      )}
      {note && (
        <p className="option-note">
          <Typed text={note} version={version} delay={400} />
        </p>
      )}
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
          . The lines that disagree are marked below.
        </Notice>
      )}
      {reference && (
        <section
          className="reconciliation-summary"
          aria-labelledby="comparison-heading"
        >
          <div className="subsection-heading">
            <h4 id="comparison-heading">Quantity on each record</h4>
            <span>Normalized to tonnes</span>
          </div>
          <div
            className="quantity-comparison"
            role="list"
            aria-label="Quantity comparison"
          >
            <div role="listitem" className="quantity-source reference">
              <span className="source-name">Purchase order</span>
              <strong>
                {number(reference.quantity)} <small>t</small>
              </strong>
              <span className="comparison-result">
                S/4HANA · PO {reference.purchase_order}
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
                    className={`quantity-source ${mismatch ? "mismatch" : "match"}`}
                  >
                    <span className="source-name">{documentTitles[type]}</span>
                    <strong>
                      {extraction ? (
                        <>
                          {number(Number(extraction.value))} <small>t</small>
                        </>
                      ) : (
                        "Not verified"
                      )}
                    </strong>
                    <span className="comparison-result">
                      {extraction
                        ? mismatch
                          ? "Does not match the PO"
                          : "Matches the PO"
                        : "Review the source"}
                    </span>
                  </div>
                );
              })}
          </div>
          <p className="panel-footnote">
            Package counts and gross weights are not treated as a stated goods
            quantity.
          </p>
        </section>
      )}
      <div className="subsection-heading">
        <h4>Source documents</h4>
        <span>
          {item.documents.documents.length} of{" "}
          {item.documents.required_documents.length} available
        </span>
      </div>
      <div className="document-stack">
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
              (e) =>
                e.document_type === type && quantityIssue?.field === e.field,
            ),
          );
          return (
            <details
              className={`document ${findings.length ? "has-finding" : ""}`}
              key={type}
              open={findings.length > 0 || compared}
            >
              <summary>
                <span className="document-name">
                  {documentTitles[type] || type}
                </span>
                <span
                  className={`document-badge ${!doc || findings.length ? "warning" : ""}`}
                >
                  {!doc
                    ? "Missing"
                    : findings.length
                      ? "Discrepancy"
                      : reconciliation
                        ? "Reviewed"
                        : "Available"}
                </span>
                <ChevronDown size={16} aria-hidden="true" />
              </summary>
              {doc ? (
                <pre>
                  {doc.text.split("\n").map((line, i) => {
                    const extraction =
                      reconciliation?.verified_extractions.find(
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
                <p className="document-findings">
                  {findings
                    .map(
                      (f) =>
                        `${f.field === "quantity" ? "Quantity" : f.field}: ${f.document_values[type]}${f.field === "quantity" ? " t" : ""} here vs ${f.purchase_order_value}${f.field === "quantity" ? " t" : ""} on the purchase order`,
                    )
                    .join(". ")}
                </p>
              )}
            </details>
          );
        })}
      </div>
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
  const scale = Math.max(
    1,
    ...item.inventory.plants.map(
      (p) =>
        Math.max(p.unrestricted_t + p.in_transit_t, p.safety_stock_t) * 1.15,
    ),
  );
  return (
    <>
      <div className="subsection-heading">
        <h4>Material {item.inventory.material}</h4>
        <span>S/4HANA (mock) · tonnes</span>
      </div>
      {item.inventory.plants.map((plant) => {
        const state =
          plant.unrestricted_t < plant.safety_stock_t
            ? "short"
            : plant.unrestricted_t === plant.safety_stock_t
              ? "at-threshold"
              : "covered";
        const spare = Math.max(0, plant.unrestricted_t - plant.safety_stock_t);
        const use = plant.consumption_t_per_day.all;
        return (
          <section className={`plant ${state}`} key={plant.plant}>
            <div className="plant-heading">
              <h4>Plant {plant.plant}</h4>
              <span className={state === "covered" ? "covered" : "short"}>
                {state === "short"
                  ? "Below safety stock"
                  : state === "at-threshold"
                    ? "At safety stock · no spare stock"
                    : `${number(spare)} t above safety stock`}
              </span>
            </div>
            <div
              className="stock-gauge"
              role="img"
              aria-label={`${number(plant.unrestricted_t)} t unrestricted, ${number(plant.in_transit_t)} t in transit, safety stock ${number(plant.safety_stock_t)} t`}
            >
              <span
                className="gauge-stock"
                style={{ width: `${(plant.unrestricted_t / scale) * 100}%` }}
              />
              {plant.in_transit_t > 0 && (
                <span
                  className="gauge-transit"
                  style={{
                    left: `${(plant.unrestricted_t / scale) * 100}%`,
                    width: `${(plant.in_transit_t / scale) * 100}%`,
                  }}
                />
              )}
              <span
                className="gauge-safety"
                style={{ left: `${(plant.safety_stock_t / scale) * 100}%` }}
              >
                <span>Safety {number(plant.safety_stock_t)} t</span>
              </span>
            </div>
            <dl className="plant-figures">
              <div>
                <dt>Unrestricted</dt>
                <dd>{number(plant.unrestricted_t)} t</dd>
              </div>
              <div>
                <dt>Safety stock</dt>
                <dd>{number(plant.safety_stock_t)} t</dd>
              </div>
              <div>
                <dt>In transit</dt>
                <dd>{number(plant.in_transit_t)} t</dd>
              </div>
              <div>
                <dt>Daily use</dt>
                <dd>
                  {number(use)} t/day
                  {use > 0 && (
                    <small> · {number(plant.unrestricted_t / use)} days</small>
                  )}
                </dd>
              </div>
            </dl>
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
          </section>
        );
      })}
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
  // The options this transfer serves: the planner picks one as they approve.
  // They differ only in which orders go first, so the choice travels with the
  // approval as its note and the transfer itself stays the validated one.
  const courses = (caseItem.plan?.options || []).filter(
    (option) => option.validation?.validation_id === action.validation_id,
  );
  const [course, setCourse] = useState(
    courses.find((option) => option.name === caseItem.plan?.recommended_option)
      ?.name ??
      courses[0]?.name ??
      "",
  );
  const approvalNote = [course && `Course: ${course}`, reason.trim()]
    .filter(Boolean)
    .join(" · ");
  return (
    <div
      className={`approval-card ${isPending ? "pending" : ""} ${action.status}`}
    >
      <div className="approval-card-heading">
        <h3>Stock transport order</h3>
        <span className={valid.valid ? "valid" : "invalid"}>
          {action.validation_id} ·{" "}
          {valid.valid ? "Validation passed" : "Validation rejected"}
        </span>
      </div>
      <div className="transfer-route">
        <div className="transfer-quantity">
          <strong>
            {number(valid.quantity)}
            <small>t</small>
          </strong>
          <span>{caseItem.inventory.material}</span>
        </div>
        <div className="transfer-leg">
          <span>From</span>
          <strong>Plant {valid.source_plant}</strong>
        </div>
        <ArrowRight size={24} aria-hidden="true" />
        <div className="transfer-leg">
          <span>To</span>
          <strong>Plant {valid.destination_plant}</strong>
        </div>
      </div>
      {!isPending && <ApprovalPlan action={action} caseItem={caseItem} />}
      <p className="approval-rationale">{caseItem.plan?.recommendation}</p>
      <p className="panel-footnote">
        Quantity and route come from the validation record. Stock is rechecked
        before the order is created.
      </p>
      {action.status === "executed" ? (
        <div className="approval-executed">
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
          <p>This plan is not currently accepting a decision.</p>
        </div>
      ) : (
        <div className="decision-desk">
          <Notice
            tone="warning"
            title="Approval creates a stock transport order"
          >
            Approve to transfer {number(valid.quantity)} t from plant{" "}
            {valid.source_plant} to plant {valid.destination_plant}. Your
            decision is recorded as {approver}.
          </Notice>
          {courses.length > 0 && (
            <fieldset className="resolve-options" disabled={disabled}>
              <legend>Course to follow</legend>
              {courses.map((option) => (
                <label className="resolve-option" key={option.name}>
                  <input
                    type="radio"
                    name={`course-${action.validation_id}`}
                    checked={course === option.name}
                    onChange={() => setCourse(option.name)}
                  />
                  <span>
                    <strong>{option.name}</strong>
                    <small>
                      {option.assessment.covered
                        ? "Covered"
                        : `${number(option.assessment.shortage_t)} t short`}
                      {" · "}
                      {number(option.assessment.coverage_days)} of{" "}
                      {number(option.assessment.required_coverage_days)} days
                      {option.assessment.deferred_orders.length > 0 &&
                        ` · defers ${option.assessment.deferred_orders
                          .map((order) => order.order_id)
                          .join(", ")}`}
                      {option.name === caseItem.plan?.recommended_option &&
                        " · Recommended"}
                    </small>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
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
          {error && (
            <div className="notice notice-error decision-error" role="alert">
              <span className="notice-mark" aria-hidden="true" />
              <div className="notice-copy">
                <strong>Decision not recorded</strong>
                <div>
                  The request failed. Review the current case before trying
                  again.
                  <details className="error-details">
                    <summary>Request details</summary>
                    {error}
                  </details>
                </div>
              </div>
            </div>
          )}
          <div className="approval-buttons">
            <p className="approval-signature">
              Signed as <strong>{approver}</strong>
              {!reason.trim() && " · a note is needed only to reject"}
            </p>
            <button
              className="reject-button"
              disabled={disabled || !reason.trim()}
              onClick={() => void onDecision(action, "rejected", reason)}
            >
              Reject
            </button>
            <button
              className="approve-button"
              disabled={disabled || !valid.valid}
              onClick={() => void onDecision(action, "approved", approvalNote)}
            >
              Approve transfer
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// An escalated case asks for a course CLEAR cannot carry out itself, such as
// deferring orders or emergency sourcing. The planner records the course they
// chose; CLEAR logs it and keeps monitoring the case.
function Resolve({
  caseItem,
  disabled,
  approver,
  error,
  onResolve,
}: {
  caseItem: Case;
  disabled: boolean;
  approver: string;
  error: string;
  onResolve: (option: string | null, note: string) => Promise<void>;
}) {
  const options = caseItem.plan?.options || [];
  const OWN = "";
  const [choice, setChoice] = useState<string>(
    caseItem.plan?.recommended_option ?? options[0]?.name ?? OWN,
  );
  const [note, setNote] = useState("");
  const own = choice === OWN;
  return (
    <div className="decision-desk resolve-desk">
      <div className="resolve-heading">
        <h3>Record your decision</h3>
        <p>
          {caseItem.status_reason ||
            "CLEAR cannot settle this case on its own."}
        </p>
      </div>
      <fieldset className="resolve-options" disabled={disabled}>
        <legend>Course to follow</legend>
        {options.map((option) => (
          <label className="resolve-option" key={option.name}>
            <input
              type="radio"
              name="resolve-option"
              checked={choice === option.name}
              onChange={() => setChoice(option.name)}
            />
            <span>
              <strong>{option.name}</strong>
              <small>
                {option.assessment.covered
                  ? "Covered"
                  : `${number(option.assessment.shortage_t)} t short`}
                {option.assessment.deferred_orders.length > 0 &&
                  ` · defers ${option.assessment.deferred_orders
                    .map((order) => order.order_id)
                    .join(", ")}`}
                {option.name === caseItem.plan?.recommended_option &&
                  " · Recommended"}
              </small>
            </span>
          </label>
        ))}
        <label className="resolve-option">
          <input
            type="radio"
            name="resolve-option"
            checked={own}
            onChange={() => setChoice(OWN)}
          />
          <span>
            <strong>Another course</strong>
            <small>Describe it in the note, e.g. emergency sourcing</small>
          </span>
        </label>
      </fieldset>
      <label className="reason-label" htmlFor="resolve-note">
        Decision note <span>{own ? "Required" : "Optional"}</span>
      </label>
      <textarea
        id="resolve-note"
        maxLength={2000}
        placeholder="What you will do and why…"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        disabled={disabled}
      />
      {error && (
        <div className="notice notice-error decision-error" role="alert">
          <span className="notice-mark" aria-hidden="true" />
          <div className="notice-copy">
            <strong>Decision not recorded</strong>
            <div>
              The request failed. Review the current case before trying again.
              <details className="error-details">
                <summary>Request details</summary>
                {error}
              </details>
            </div>
          </div>
        </div>
      )}
      <div className="approval-buttons">
        <p className="approval-signature">
          Signed as <strong>{approver}</strong> · CLEAR records the decision;
          you carry it out
        </p>
        <button
          className="approve-button"
          disabled={disabled || (own && !note.trim())}
          onClick={() => void onResolve(own ? null : choice, note)}
        >
          Record decision
        </button>
      </div>
    </div>
  );
}

function ResolutionNote({ resolution }: { resolution: Resolution }) {
  return (
    <div className="approval-executed resolution-note">
      <div>
        <strong>
          {resolution.approver} chose{" "}
          {resolution.option || "a course outside the plan’s options"}
        </strong>
        {resolution.note && <p>{resolution.note}</p>}
        <p>
          Recorded {time(resolution.at)}. CLEAR keeps monitoring; the next
          logistics event reopens the assessment.
        </p>
      </div>
    </div>
  );
}

// One transfer can sit under several options: they share the validated
// transfer and differ only in which orders are served while the shipment is
// held. Only the transfer is an ERP write, so it is the one thing approved;
// the order priority is the planner's to apply. This says which option the
// transfer carries out and which other options lean on it too.
function ApprovalPlan({ action, caseItem }: { action: Action; caseItem: Case }) {
  const options = (caseItem.plan?.options || []).filter(
    (option) => option.validation?.validation_id === action.validation_id,
  );
  if (!options.length) return null;
  const chosen =
    options.find((option) => option.name === caseItem.plan?.recommended_option) ||
    options[0];
  const others = options.filter((option) => option !== chosen);
  const deferred = chosen.assessment.deferred_orders.map((order) => order.order_id);
  return (
    <div className="approval-plan">
      <p>
        <strong>Carries out: {chosen.name}</strong>
        {chosen.name === caseItem.plan?.recommended_option && (
          <span className="option-mark">Recommended</span>
        )}
      </p>
      <p>
        {number(chosen.assessment.coverage_days)} of{" "}
        {number(chosen.assessment.required_coverage_days)} days covered
        {deferred.length
          ? `; ${deferred.join(", ")} wait until the shipment clears.`
          : "; no order waits."}{" "}
        Only the transfer is written to S/4HANA; which orders go first is yours
        to apply.
      </p>
      {others.length > 0 && (
        <p className="approval-plan-note">
          {others.map((option) => option.name).join(" and ")}{" "}
          {others.length > 1 ? "use" : "uses"} the same transfer and{" "}
          {others.length > 1 ? "defer" : "defers"} more orders, so there is
          nothing else to approve.
        </p>
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
    <section className="timeline-panel" aria-labelledby="timeline-heading">
      <div className="rail-heading">
        <h3 id="timeline-heading">Agent activity</h3>
        <span className={running ? "activity-live" : ""}>
          {running ? "Live" : `${visibleEntries.length} steps`}
        </span>
      </div>
      <p className="timeline-caption">
        Every agent step, tool result and decision is recorded here.
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
        tabIndex={0}
      >
        {visibleEntries.map((entry) => (
          <div className={`timeline-entry ${entry.flag || ""}`} key={entry.seq}>
            <span className="timeline-mark" aria-hidden="true" />
            <div className="timeline-entry-body">
              <div className="timeline-entry-heading">
                <strong>{entry.actor}</strong>
                <time dateTime={entry.at}>{time(entry.at)}</time>
              </div>
              {entry.flag && (
                <span className="timeline-flag">
                  {entry.flag === "rejected"
                    ? "Validator rejected"
                    : entry.flag === "write"
                      ? "ERP write"
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
          </div>
        ))}
        {!entries.length && (
          <div className="timeline-empty">Waiting for the first signal…</div>
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
          Jump to latest <ChevronDown size={14} />
        </button>
      )}
    </section>
  );
}
