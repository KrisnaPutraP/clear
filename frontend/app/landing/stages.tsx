"use client";

import { useState, type CSSProperties, type ReactNode } from "react";
import type { Case } from "../../lib/types";
import { Harbour } from "../harbour";

// One case, scenario S1, walked through its four stages. The harbour gets a
// minimal case in each stage's state and plays it out the way the workspace
// does; the fragment beside it is that stage's piece of the real interface.
// Every number is from the S1 seed (docs/examples/case_s1.json).
const discrepancy = { reconciliation: { discrepancies: [{ field: "quantity" }] } };
const action = (status: string) => ({
  plan: { actions: [{ status, validation: { valid: true } }] },
});
const scene = (state: object) => state as unknown as Case;

type Stage = {
  name: string;
  clause: string;
  text: string;
  item: Case;
  running: boolean;
  fragment: ReactNode;
};

const stages: Stage[] = [
  {
    name: "Investigate",
    clause: "First, read every document",
    text: "An event arrives: SHP-1001 is held at customs. The agents read the invoice, the packing list, the bill of lading and the purchase order, and code compares them.",
    item: scene({ status: "analyzing", plan: null, ...discrepancy }),
    running: true,
    fragment: (
      <div className="ui-card" data-ui>
        <p className="ui-title">Quantity · REC-0001</p>
        <table className="ui-table">
          <tbody>
            <tr>
              <th scope="row">Purchase order</th>
              <td>120 t</td>
            </tr>
            <tr>
              <th scope="row">Commercial invoice</th>
              <td>120 t</td>
            </tr>
            <tr className="ui-bad">
              <th scope="row">Packing list</th>
              <td>112 t</td>
            </tr>
          </tbody>
        </table>
        <p className="ui-note">Quantity differs in the packing list · deterministic check</p>
      </div>
    ),
  },
  {
    name: "Assess impact",
    clause: "Then, count the days left",
    text: "Plant 1100 has 1.9 days of bleaching agent; the hold is expected to take about 3. The validator turns down the first idea, a 32 t transfer, because plant 1200 would fall under its safety stock.",
    item: scene({ status: "analyzing", plan: { actions: [] }, ...discrepancy }),
    running: false,
    fragment: (
      <div className="ui-card" data-ui>
        <p className="ui-title">Stock coverage · CHEM-BX40</p>
        <p className="ui-figure">
          1.9 <span>of 3.5 days needed</span>
        </p>
        <div className="ui-bar" role="img" aria-label="1.9 of 3.5 days covered">
          <span style={{ width: `${(1.9 / 3.5) * 100}%` }} />
        </div>
        <p className="ui-bad-line">
          VAL-0001 rejected: plant 1200 would fall to 28 t, below its safety
          stock of 40 t. Max feasible 20 t.
        </p>
      </div>
    ),
  },
  {
    name: "Review & approve",
    clause: "Next, a planner signs it",
    text: "CLEAR proposes the 20 t the rules allow, with critical and high orders served first: 3.87 days covered. Nothing is written to S/4HANA until a named planner approves.",
    item: scene({ status: "awaiting_approval", ...action("awaiting_approval"), ...discrepancy }),
    running: false,
    fragment: (
      <div className="ui-card ui-decision" data-ui>
        <p className="ui-title">Stock transport order · VAL-0002 passed</p>
        <p className="ui-figure">
          20 t <span>plant 1200 → plant 1100</span>
        </p>
        <div className="ui-buttons">
          <span className="ui-button">Reject</span>
          <span className="ui-button ui-approve">Approve transfer</span>
        </div>
        <p className="ui-note">Signed as Rina Hartono, demo planner</p>
      </div>
    ),
  },
  {
    name: "Monitor",
    clause: "Last, keep watching",
    text: "The order is created from the validation, stock is checked again, and CLEAR keeps the case open. A new event, such as an ETA slip, starts the assessment over.",
    item: scene({ status: "monitoring", ...action("executed"), ...discrepancy }),
    running: false,
    fragment: (
      <div className="ui-card" data-ui>
        <p className="ui-title">Order created · 4500001023</p>
        <table className="ui-table">
          <tbody>
            <tr>
              <th scope="row">Plant 1100</th>
              <td>38 t + 20 t in transit</td>
            </tr>
            <tr>
              <th scope="row">Plant 1200</th>
              <td>40 t, at safety stock</td>
            </tr>
          </tbody>
        </table>
        <p className="ui-note">Next: the transfer’s arrival and the customs response</p>
      </div>
    ),
  },
];

export function Stages() {
  const [index, setIndex] = useState(0);
  const stage = stages[index];
  return (
    <section className="chapter stages" id="how-it-works" data-ink="paper">
      <div className="stages-clause">
        <h2 className="step-2" key={stage.clause} aria-live="polite">
          {stage.clause}
        </h2>
        <p className="stages-text reveal" key={stage.text}>
          {stage.text}
        </p>
      </div>
      <div className="stages-stage">
        <div className="stages-harbour">
          <Harbour item={stage.item} running={stage.running} />
        </div>
        <div className="stages-fragment" key={stage.name}>
          {stage.fragment}
        </div>
      </div>
      <div className="stages-control">
        <label className="sr-only" htmlFor="stage-range">
          Stage of the case
        </label>
        <input
          id="stage-range"
          type="range"
          min={0}
          max={stages.length - 1}
          step={1}
          value={index}
          aria-valuetext={stage.name}
          onChange={(e) => setIndex(Number(e.target.value))}
          style={{ "--passed": `${(index / (stages.length - 1)) * 100}%` } as CSSProperties}
        />
        <ol className="stages-names">
          {stages.map((item, i) => (
            <li key={item.name}>
              <button
                className={i === index ? "current" : ""}
                aria-pressed={i === index}
                onClick={() => setIndex(i)}
              >
                {item.name}
              </button>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
