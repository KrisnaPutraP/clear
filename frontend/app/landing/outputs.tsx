"use client";

import { useState, type ReactNode } from "react";

// What a case leaves behind, each as the sheet it is. Figures are scenario
// S1 from the seed (docs/examples/case_s1.json); the data is synthetic.
type Output = { name: string; width: "wide" | "narrow"; sheet: ReactNode };

const outputs: Output[] = [
  {
    name: "Document check",
    width: "wide",
    sheet: (
      <>
        <header className="sheet-head">
          <strong>Reconciliation REC-0001</strong>
          <span>SHP-1001 · PO 4500001021 · 11 Oct 2026</span>
        </header>
        <table className="sheet-table">
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">Purchase order</th>
              <th scope="col">Invoice</th>
              <th scope="col">Packing list</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Material</th>
              <td>CHEM-BX40</td>
              <td>CHEM-BX40</td>
              <td>CHEM-BX40</td>
            </tr>
            <tr className="sheet-bad">
              <th scope="row">Quantity</th>
              <td>120 t</td>
              <td>120 t</td>
              <td>112 t</td>
            </tr>
          </tbody>
        </table>
        <p className="sheet-verdict">
          The packing list states 8 t less than the invoice and the purchase
          order. Each value was read with its quote from the document and
          compared by code, not by the model.
        </p>
      </>
    ),
  },
  {
    name: "Recovery plan",
    width: "wide",
    sheet: (
      <>
        <header className="sheet-head">
          <strong>Recovery plan · CASE-0001</strong>
          <span>Resolution estimate 3 days · baseline median</span>
        </header>
        <table className="sheet-table">
          <thead>
            <tr>
              <th scope="col">Option</th>
              <th scope="col">Coverage</th>
              <th scope="col">Shortage</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Current plan, all orders</th>
              <td>1.9 of 3.5 days</td>
              <td>32 t</td>
            </tr>
            <tr>
              <th scope="row">Transfer 20 t from 1200</th>
              <td>2.9 of 3.5 days</td>
              <td>12 t</td>
            </tr>
            <tr className="sheet-chosen">
              <th scope="row">20 t + critical and high orders</th>
              <td>3.87 of 3.5 days</td>
              <td>None</td>
            </tr>
          </tbody>
        </table>
        <p className="sheet-verdict">
          Recommended: transfer the feasible 20 t and serve critical and high
          orders until the shipment clears. PRD-1106 and PRD-1107 wait.
        </p>
      </>
    ),
  },
  {
    name: "Transfer order",
    width: "narrow",
    sheet: (
      <>
        <header className="sheet-head">
          <strong>STO 4500001023</strong>
          <span>Type UB · created 11 Oct 2026</span>
        </header>
        <dl className="sheet-list">
          <div>
            <dt>Material</dt>
            <dd>CHEM-BX40</dd>
          </div>
          <div>
            <dt>Quantity</dt>
            <dd>20 t</dd>
          </div>
          <div>
            <dt>From → to</dt>
            <dd>Plant 1200 → plant 1100</dd>
          </div>
          <div>
            <dt>Lead time</dt>
            <dd>1 day</dd>
          </div>
          <div>
            <dt>Validation</dt>
            <dd>VAL-0002, passed</dd>
          </div>
          <div>
            <dt>Approval</dt>
            <dd>APR-0001, Rina Hartono</dd>
          </div>
        </dl>
      </>
    ),
  },
  {
    name: "Escalation",
    width: "narrow",
    sheet: (
      <>
        <header className="sheet-head">
          <strong>Needs a planner’s call</strong>
          <span>After the ETA slip to 1 Nov, 14:00</span>
        </header>
        <p className="sheet-verdict">
          Decide on emergency sourcing for the deferred high and normal
          orders.
        </p>
        <dl className="sheet-list">
          <div>
            <dt>Recommended</dt>
            <dd>Critical orders only, transfer in transit</dd>
          </div>
          <div>
            <dt>Further transfer</dt>
            <dd>VAL-0003 rejected, max 0 t</dd>
          </div>
        </dl>
      </>
    ),
  },
];

export function Outputs() {
  const [index, setIndex] = useState(0);
  const output = outputs[index];
  return (
    <section className="chapter outputs" id="outputs" data-ink="blue">
      <div className="outputs-index">
        <h2 className="step-3">What a case leaves behind</h2>
        <ul>
          {outputs.map((item, i) => (
            <li key={item.name}>
              <button
                className={`step-2 ${i === index ? "current" : ""}`}
                aria-pressed={i === index}
                onClick={() => setIndex(i)}
              >
                {item.name}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="outputs-stage">
        <article
          className={`sheet ${output.width}`}
          key={output.name}
          data-ui
          aria-label={output.name}
        >
          {output.sheet}
        </article>
      </div>
    </section>
  );
}
