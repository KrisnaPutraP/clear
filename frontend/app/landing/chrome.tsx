"use client";

import { useEffect, useState } from "react";

// The bar takes the field and ink of the chapter beneath it, switching as each
// chapter's edge passes under it. Everything else on the page stays put.
export function Header() {
  const [ink, setInk] = useState("night");
  useEffect(() => {
    const fields = [...document.querySelectorAll<HTMLElement>("main [data-ink], footer[data-ink]")];
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries)
          if (entry.isIntersecting)
            setInk((entry.target as HTMLElement).dataset.ink || "night");
      },
      { rootMargin: "-36px 0px -96% 0px" },
    );
    fields.forEach((field) => observer.observe(field));
    return () => observer.disconnect();
  }, []);
  return (
    <header className="landing-bar" data-ink={ink}>
      <a className="landing-mark" href="#top" aria-label="CLEAR, back to the top">
        {/* The bar changes field per chapter; each ship suits one kind. */}
        <img className="ship-on-dark" src="/clear-logo-mark-dark.svg" width={57} height={28} alt="" />
        <img className="ship-on-light" src="/clear-logo-mark.svg" width={57} height={28} alt="" />
        CLEAR
      </a>
      <nav aria-label="Sections">
        <a href="#how-it-works">How it works</a>
        <a href="#outputs">Outputs</a>
        <a href="#safeguards">Safeguards</a>
        <a href="#stack">Stack</a>
      </nav>
      <details className="landing-menu">
        <summary>Menu</summary>
        <div>
          <a href="#how-it-works">How it works</a>
          <a href="#outputs">Outputs</a>
          <a href="#safeguards">Safeguards</a>
          <a href="#stack">Stack</a>
        </div>
      </details>
      <a className="landing-action" href="/workspace">
        Open the workspace
      </a>
    </header>
  );
}

// Each section's parts rise in once as it enters: heading, then text, then
// picture, by their --i order. Without script nothing is hidden.
export function Reveal() {
  useEffect(() => {
    const root = document.documentElement;
    // With reduced motion the footage rests on its poster frame.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
      document.querySelectorAll("video").forEach((video) => video.pause());
    root.classList.add("reveal-ready");
    const parts = [...document.querySelectorAll<HTMLElement>(".reveal")];
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries)
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            observer.unobserve(entry.target);
          }
      },
      { rootMargin: "0px 0px -12% 0px" },
    );
    parts.forEach((part) => observer.observe(part));
    return () => {
      observer.disconnect();
      root.classList.remove("reveal-ready");
    };
  }, []);
  return null;
}

const events = [
  { id: "S1-DOC-HOLD", label: "customs hold" },
  { id: "S1-ETA-SLIP", label: "ETA slip" },
  { id: "S2-CONGESTION", label: "port congestion" },
];

// The closing sentence has a blank: pick the exception, and CLEAR opens the
// workspace with that demo event ready to send.
export function Handover() {
  const [event, setEvent] = useState(events[0].id);
  return (
    <form
      className="handover"
      action="/workspace"
      onSubmit={(e) => {
        e.preventDefault();
        window.location.assign(`/workspace?event=${encodeURIComponent(event)}`);
      }}
    >
      <h2 className="step-2">
        Hand the next{" "}
        <label className="sr-only" htmlFor="handover-event">
          Exception
        </label>
        <select
          id="handover-event"
          name="event"
          value={event}
          onChange={(e) => setEvent(e.target.value)}
        >
          {events.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>{" "}
        to <button type="submit">CLEAR</button>
      </h2>
      <p>
        Opens the workspace with this demo event ready to send. All business
        data is synthetic.
      </p>
    </form>
  );
}
