import type { Metadata } from "next";
import type { CSSProperties } from "react";
import { Sky } from "./sky";
import { Header, Handover, Reveal } from "./landing/chrome";
import { Outputs } from "./landing/outputs";
import { Stages } from "./landing/stages";
import "./landing.css";

export const metadata: Metadata = {
  title: "CLEAR",
  description:
    "AI agents turn a held import shipment into one validated stock transfer that a planner approves.",
};

// The hero's vessel: the workspace's COOKUSAN SHIP, riding the seam between
// the night and the sea.
function Ship() {
  return (
    <svg className="hero-ship" viewBox="-10 -170 270 210" aria-hidden="true">
      <g className="hero-ship-bob">
        <rect x={216} y={-150} width={3} height={76} fill="#7a8aa6" />
        <rect x={200} y={-140} width={36} height={3} fill="#7a8aa6" />
        {/* The placement sits one level above the flutter, so the
            animation's transform cannot carry the pennant off the mast. */}
        <g transform="translate(219 -150)">
          <g className="hero-pennant">
            <polygon points="0,0 24,4 0,8" fill="#e0392f" />
          </g>
        </g>
        <rect x={20} y={-70} width={30} height={22} fill="#e0392f" />
        <rect x={52} y={-70} width={30} height={22} fill="#eef1f6" />
        <rect x={84} y={-70} width={30} height={22} fill="#f2c014" />
        <rect x={116} y={-70} width={30} height={22} fill="#1c4597" />
        <rect x={36} y={-94} width={30} height={22} fill="#1c4597" />
        <rect x={68} y={-94} width={30} height={22} fill="#e0392f" />
        <rect x={100} y={-94} width={30} height={22} fill="#eef1f6" />
        <rect x={168} y={-92} width={34} height={44} fill="#eef1f6" />
        <rect x={174} y={-84} width={7} height={6} fill="#0b101b" />
        <rect x={186} y={-84} width={7} height={6} fill="#0b101b" />
        <rect x={198} y={-90} width={14} height={16} fill="#b8261d" />
        <path d="M0 -46 H246 L226 0 H16 Z" fill="#0b101b" />
        <path d="M12 -8 H232 L228 2 H16 Z" fill="#e0392f" />
        <text x={56} y={-22} className="hero-hull">
          COOKUSAN SHIP
        </text>
      </g>
    </svg>
  );
}

const credits = [
  {
    title: "Drammen havn blue cranes (2)",
    by: "Peulle",
    licence: "CC BY-SA 4.0",
    licenceUrl: "https://creativecommons.org/licenses/by-sa/4.0",
    page: "https://commons.wikimedia.org/wiki/File:Drammen_havn_blue_cranes_(2).jpg",
  },
  {
    title: "Container terminal by night, Oslo",
    by: "Grzegorz Wysocki",
    licence: "CC BY 3.0",
    licenceUrl: "https://creativecommons.org/licenses/by/3.0",
    page: "https://commons.wikimedia.org/wiki/File:Container_terminal_by_night,_Oslo.jpg",
  },
  {
    title: "Aerial views at night of Cork Container Terminal (CCT) in Ringaskiddy",
    by: "FILMING CORK",
    changes: "trimmed to 12 seconds, sound removed",
    licence: "CC BY 3.0",
    licenceUrl: "https://creativecommons.org/licenses/by/3.0",
    page: "https://commons.wikimedia.org/wiki/File:Aerial_views_at_night_of_Cork_Container_Terminal_(CCT)_in_Ringaskiddy,_County_Cork,_Ireland.webm",
  },
];

const locks = [
  {
    name: "A validated ID",
    text: "The write tool takes a validation ID, never a quantity typed by a model.",
  },
  {
    name: "Safety-stock rules",
    text: "The validator refuses any transfer that leaves a plant under its safety stock.",
  },
  {
    name: "A named planner",
    text: "No transfer order exists without an approval record with a person’s name on it.",
  },
  {
    name: "A gateway policy",
    text: "A Cedar policy at AgentCore Gateway, outside the agents, guards the one write.",
  },
  {
    name: "A last check in code",
    text: "Before S/4HANA is touched, the write reads the validation and the approval again.",
  },
];

export default function Landing() {
  return (
    <div className="landing" id="top">
      <Sky />
      <Reveal />
      <Header />
      <main>
        <section className="hero" data-ink="night" aria-labelledby="hero-title">
          <svg className="hero-moon" viewBox="0 0 40 40" aria-hidden="true">
            <circle cx={20} cy={20} r={18} fill="#f3ead2" />
            <circle cx={28} cy={14} r={16} fill="#121a2b" />
          </svg>
          <div className="hero-sea" aria-hidden="true" />
          <Ship />
          <h1 className="hero-title" id="hero-title">
            <span className="hero-line">Clear</span>{" "}
            <span className="hero-line">the hold</span>
          </h1>
          <p className="hero-lede step-4">
            AI agents turn a held import shipment into one validated stock
            transfer, and a planner approves it.
          </p>
        </section>

        <Stages />

        <Outputs />

        <section className="chapter locks" id="safeguards" data-ink="night">
          <div className="locks-board">
            <div className="lock lock-head reveal">
              <h2 className="step-2">Five locks on every write</h2>
            </div>
            {locks.map((lock, i) => (
              <div className="lock reveal" key={lock.name} style={{ "--i": i + 1 } as CSSProperties}>
                <h3 className="step-3">{lock.name}</h3>
                <p>{lock.text}</p>
              </div>
            ))}
            <figure className="lock lock-picture reveal" style={{ "--i": 6 } as CSSProperties}>
              <img
                src="/landing/terminal-oslo.jpg"
                width={1369}
                height={1024}
                alt="A container terminal lit orange at night, Oslo"
                loading="lazy"
              />
              <figcaption>Ten proposals refused by the validator in the 12 October live run</figcaption>
            </figure>
          </div>
        </section>

        <section className="chapter signed" data-ink="yellow" aria-labelledby="signed-title">
          <h2 className="step-2 reveal" id="signed-title">
            Nothing ships unsigned
          </h2>
          <div className="signed-figure">
            <p className="step-1 reveal" style={{ "--i": 1 } as CSSProperties}>
              100<sup>%</sup>
            </p>
            <p className="signed-caption reveal" style={{ "--i": 2 } as CSSProperties}>
              of stock transfers in a live run of 20 unscripted scenario
              variants were created only after a named planner approved them.
            </p>
          </div>
          <p className="signed-source">
            Live run, 12 October 2026, Claude Sonnet 4.6 on SAP AI Core
          </p>
        </section>

        <section className="chapter stack" id="stack" data-ink="paper">
          <div className="stack-panel">
            <div className="stack-lead">
              <h2 className="step-2 reveal">Built on SAP and AWS</h2>
              <figure className="stack-picture reveal" style={{ "--i": 2 } as CSSProperties}>
                <img
                  src="/landing/cranes-drammen.jpg"
                  width={1920}
                  height={1225}
                  alt="Two harbour cranes lit blue at night, reflected in the water, Drammen"
                  loading="lazy"
                />
              </figure>
            </div>
            <div className="stack-text">
              <div className="reveal" style={{ "--i": 1 } as CSSProperties}>
                <h3 className="step-3">The agents</h3>
                <p>
                  An orchestrator and three specialists, built with Strands,
                  run Claude Sonnet 4.6 on SAP AI Core. SAP-RPT-1.6 predicts
                  how long a hold lasts. In the live run a plan took a median
                  of 80 seconds.
                </p>
              </div>
              <div className="reveal" style={{ "--i": 2 } as CSSProperties}>
                <h3 className="step-3">The guardrails</h3>
                <p>
                  Tools sit behind AgentCore Gateway with Cedar policies, on
                  Lambda and DynamoDB. Purchase orders and stock use the field
                  names of SAP S/4HANA’s own APIs.
                </p>
              </div>
              <a className="landing-button reveal" href="/workspace" style={{ "--i": 3 } as CSSProperties}>
                Open the workspace
              </a>
            </div>
          </div>
        </section>

        <section className="chapter handover-field" data-ink="sea">
          <Handover />
          <figure className="handover-picture">
            <video
              src="/landing/terminal-cork.mp4"
              poster="/landing/terminal-cork.jpg"
              width={854}
              height={480}
              autoPlay
              muted
              loop
              playsInline
              preload="metadata"
              aria-label="Rows of containers in a terminal at night, filmed from the air, Cork"
            />
          </figure>
        </section>
      </main>

      <footer className="landing-footer" data-ink="deep">
        <p className="footer-name" aria-hidden="true">
          CLEAR
        </p>
        <div className="footer-row">
          <ul className="footer-places">
            <li>
              <a href="/workspace">The workspace</a>
            </li>
            <li>
              <a href="#how-it-works">How a case runs</a>
            </li>
          </ul>
          <div className="footer-about">
            <p>
              Cookusan Logistics Exception Agentic Resolver, by team Cookusan.
              All shipments, plants, orders and planners shown are synthetic
              demo data.
            </p>
            <p className="credits">
              Pictures and footage:{" "}
              {credits.map((credit, i) => (
                <span key={credit.page}>
                  <a href={credit.page}>“{credit.title}”</a> by {credit.by},{" "}
                  <a href={credit.licenceUrl}>{credit.licence}</a>, via
                  Wikimedia Commons
                  {"changes" in credit ? `, ${credit.changes}` : ""}
                  {i < credits.length - 1 ? "; " : "."}
                </span>
              ))}
            </p>
          </div>
        </div>
        <div className="footer-last">
          <span>CLEAR · Demo Day, 31 October 2026</span>
          <a href="#top">Back to the top</a>
        </div>
      </footer>
    </div>
  );
}
