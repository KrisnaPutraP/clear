import type { CSSProperties } from "react";
import type { Case } from "../lib/types";
import { FlagShape, type FlagCode } from "./flags";

// A port of discharge at dusk, drawn in flat shapes and driven by the case:
// the vessel rides at anchor flying the case's signal flags, the silos at the
// case's plants hold their real stock against the safety line, and an
// approved transfer drives from the source plant to the one by the port. The art is decoration for
// the facts beside it, so the whole scene is hidden from assistive tech.

const W = 1200;
const H = 340;
const SKY = 90; // headroom above the scene for the case title
const GROUND = 268;
const SEA = 236;

const ink = {
  // The top band is the page ground, so the sky has no edge.
  sky: ["#121a2b", "#1b2742", "#253556", "#33496f"],
  glow: "#e9925a",
  distant: "#2a3a5c",
  sea: "#1a3152",
  seaDeep: "#142843",
  ripple: "#4f74a8",
  land: "#232a37",
  quay: "#333a48",
  dark: "#10141c",
  steel: "#4b5468",
  lit: "#ffd27a",
  white: "#e8ebf0",
  red: "var(--signal-red)",
  yellow: "var(--signal-yellow)",
  blue: "var(--flag-blue)",
};

type Plant = Case["inventory"]["plants"][number];

function Silo({
  x,
  plant,
  scale,
  index,
}: {
  x: number;
  plant: Plant;
  scale: number;
  index: number;
}) {
  const top = 150;
  const height = GROUND - top;
  const level = (plant.unrestricted_t / scale) * height;
  const transit = (plant.in_transit_t / scale) * height;
  const safety = GROUND - (plant.safety_stock_t / scale) * height;
  const low = plant.unrestricted_t <= plant.safety_stock_t;
  return (
    <g className="silo">
      <rect x={x} y={top} width={46} height={height} rx={3} fill={ink.steel} />
      <rect
        x={x + 4}
        y={top + 4}
        width={38}
        height={height - 4}
        fill={ink.dark}
      />
      <rect
        className="silo-level"
        x={x + 4}
        y={GROUND - level}
        width={38}
        height={level}
        fill={low ? ink.red : "#5b8ee0"}
        style={{ "--delay": `${index * 120}ms` } as CSSProperties}
      />
      {transit > 0 && (
        <rect
          className="silo-transit"
          x={x + 4}
          y={GROUND - level - transit}
          width={38}
          height={transit}
          fill="#5b8ee0"
          opacity={0.45}
        />
      )}
      <line
        x1={x - 6}
        x2={x + 52}
        y1={safety}
        y2={safety}
        stroke={ink.white}
        strokeWidth={2}
        strokeDasharray="5 4"
      />
      <path
        d={`M${x} ${top + 2} Q${x + 23} ${top - 16} ${x + 46} ${top + 2}`}
        fill={ink.steel}
      />
    </g>
  );
}

function Factory({
  x,
  plant,
  scale,
  receiving,
}: {
  x: number;
  plant: Plant;
  scale: number;
  receiving: boolean;
}) {
  return (
    <g>
      <path
        d={`M${x} ${GROUND} V206 l22 -14 v14 l22 -14 v14 l22 -14 v14 l22 -14 V${GROUND} Z`}
        fill={ink.dark}
      />
      {[0, 1, 2, 3].map((i) => (
        <rect
          key={i}
          className={i % 2 ? "window" : "window late"}
          x={x + 10 + i * 20}
          y={226}
          width={10}
          height={8}
          fill={ink.lit}
        />
      ))}
      <rect x={x + 70} y={150} width={9} height={60} fill={ink.dark} />
      <g className="smoke">
        <circle cx={x + 74} cy={142} r={6} fill="#56617a" />
        <circle cx={x + 82} cy={130} r={8} fill="#56617a" opacity={0.7} />
        <circle cx={x + 92} cy={116} r={10} fill="#56617a" opacity={0.4} />
      </g>
      <Silo x={x + 100} plant={plant} scale={scale} index={0} />
      <text className="scene-label" x={x + 4} y={GROUND + 26}>
        PLANT {plant.plant}
      </text>
      <text className="scene-figure" x={x + 4} y={GROUND + 46}>
        {plant.unrestricted_t} t
        <tspan className="scene-note">
          {" "}
          · safety {plant.safety_stock_t} t
          {plant.in_transit_t > 0 ? ` · ${plant.in_transit_t} t arriving` : ""}
        </tspan>
      </text>
      {receiving && (
        <circle
          className="beacon"
          cx={x + 123}
          cy={136}
          r={4}
          fill={ink.yellow}
        />
      )}
    </g>
  );
}

function Truck({ quantity }: { quantity: number }) {
  return (
    <g>
      <rect x={0} y={-22} width={44} height={18} rx={9} fill={ink.white} />
      <rect x={6} y={-18} width={32} height={3} fill={ink.blue} />
      <path d="M46 -4 V-20 h10 l8 9 V-4 Z" fill={ink.red} />
      <rect x={52} y={-17} width={6} height={5} fill={ink.lit} />
      <circle cx={12} cy={-2} r={5} fill={ink.dark} />
      <circle cx={34} cy={-2} r={5} fill={ink.dark} />
      <circle cx={56} cy={-2} r={5} fill={ink.dark} />
      <text className="scene-tag" x={22} y={-28} textAnchor="middle">
        {quantity} t
      </text>
    </g>
  );
}

function Containers({
  x,
  y,
  rows,
}: {
  x: number;
  y: number;
  rows: string[][];
}) {
  return (
    <g>
      {rows.map((row, r) =>
        row.map((fill, c) => (
          <g key={`${r}-${c}`}>
            <rect
              x={x + c * 26}
              y={y - (r + 1) * 12}
              width={25}
              height={11}
              fill={fill}
            />
            <rect
              x={x + c * 26 + 3}
              y={y - (r + 1) * 12 + 2}
              width={19}
              height={1.5}
              fill="rgb(0 0 0 / 0.18)"
            />
          </g>
        )),
      )}
    </g>
  );
}

function Vessel({
  flags,
  name,
  far,
  running,
}: {
  flags: FlagCode[];
  name: string;
  far: boolean;
  running: boolean;
}) {
  const cargo = [ink.red, ink.blue, ink.yellow, ink.white, ink.blue, ink.red];
  // While the agents work the vessel is under way offshore; when they finish
  // it glides in to the anchorage off the crane and drops its anchor. A held
  // or delayed vessel stays out at sea. It never berths: that would claim a
  // customs release the case does not have.
  const position = running
    ? "translate(1040px, 254px) scale(0.6)"
    : far
      ? "translate(980px, 252px) scale(0.62)"
      : "translate(880px, 284px) scale(1)";
  return (
    <g
      className={`vessel ${running ? "sailing" : "anchored"}`}
      style={{ transform: position }}
    >
      <g className="bob">
        {running ? (
          <g className="wake">
            <path d="M-4 4 q-10 -2 -16 -10" stroke={ink.white} strokeWidth={2} fill="none" />
            <path d="M-2 8 q-14 -1 -24 -8" stroke={ink.white} strokeWidth={1.5} fill="none" opacity={0.6} />
            {[0, 1, 2, 3].map((i) => (
              <line
                key={i}
                className="wake-line"
                x1={240}
                x2={420}
                y1={-2 + i * 5}
                y2={-2 + i * 5}
                stroke={ink.white}
                strokeWidth={2}
                strokeDasharray={`${14 + i * 6} ${22 + i * 8}`}
                opacity={0.5 - i * 0.1}
                style={{ "--d": `${0.8 + i * 0.3}s` } as CSSProperties}
              />
            ))}
          </g>
        ) : (
          <path className="anchor-chain" d="M14 0 L-6 30" stroke={ink.steel} strokeWidth={2} />
        )}
        <path d="M0 -26 H232 L214 6 H18 Z" fill={ink.dark} />
        <path d="M6 -6 H228 L222 4 H12 Z" fill="#b8261d" />
        <text className="hull-name" x={44} y={-12}>
          {name.toUpperCase()}
        </text>
        {cargo.map((fill, i) => (
          <rect
            key={i}
            x={30 + i * 26}
            y={-50}
            width={25}
            height={23}
            fill={fill}
          />
        ))}
        {cargo.slice(0, 4).map((fill, i) => (
          <rect
            key={`t${i}`}
            x={56 + i * 26}
            y={-72}
            width={25}
            height={21}
            fill={i % 2 ? ink.white : fill}
          />
        ))}
        <rect x={190} y={-74} width={34} height={48} fill={ink.white} />
        {[0, 1, 2].map((i) => (
          <rect
            key={i}
            x={194 + i * 10}
            y={-66}
            width={7}
            height={6}
            fill={ink.dark}
          />
        ))}
        <rect x={198} y={-90} width={14} height={16} fill="#b8261d" />
        {/* mast, yard and the hoist */}
        <rect x={216} y={-150} width={3} height={76} fill={ink.steel} />
        <rect x={200} y={-140} width={36} height={3} fill={ink.steel} />
        <circle
          className="masthead"
          cx={217.5}
          cy={-152}
          r={2.5}
          fill={ink.lit}
        />
        <line
          x1={234}
          y1={-138}
          x2={234}
          y2={-138 + flags.length * 17 + 2}
          stroke={ink.white}
          strokeWidth={1}
        />
        {flags.map((code, i) => (
          <g
            key={`${code}-${i}`}
            className={`mast-flag ${running ? "flying" : ""}`}
            transform={`translate(235 ${-136 + i * 17})`}
            style={{ "--i": i } as CSSProperties}
          >
            {/* CSS animates this group; the scale lives one level down so
                the animation's transform cannot replace it. */}
            <g>
              <g transform="scale(0.36)">
                <FlagShape code={code} />
              </g>
            </g>
          </g>
        ))}
      </g>
    </g>
  );
}

export function Harbour({
  item,
  running,
}: {
  item: Case | null;
  running: boolean;
}) {
  const plants = item?.inventory.plants || [];
  const byId = (id: string) => plants.find((p) => p.plant === id);
  const scale = Math.max(
    1,
    ...plants.map(
      (p) =>
        Math.max(p.unrestricted_t + p.in_transit_t, p.safety_stock_t) * 1.25,
    ),
  );
  const action = item?.plan?.actions.find((a) => a.validation.valid) || null;
  const delivered = action?.status === "executed";
  const proposed = action && !delivered && item?.status === "awaiting_approval";
  const driving = item?.status === "executing";
  const customs = Boolean(item?.reconciliation?.discrepancies.length);
  const congestion = Boolean(
    item && !customs && item.plan && !item.plan.actions.length,
  );
  const statusFlag: FlagCode | null = item
    ? (
        {
          analyzing: "answer",
          awaiting_approval: "K",
          executing: "P",
          monitoring: "C",
          needs_human_decision: "V",
        } as const
      )[item.status]
    : null;
  const flags: FlagCode[] = [
    ...(customs ? (["Q"] as FlagCode[]) : []),
    ...(statusFlag ? [statusFlag] : []),
  ];
  // The plant at risk stands by the port; the plant that can give stock
  // stands inland, so a transfer always drives toward the port.
  const coverage = (p: Plant) =>
    p.unrestricted_t / Math.max(p.consumption_t_per_day.all || 0, 0.001);
  const near =
    (action && byId(action.validation.destination_plant)) ||
    [...plants].sort((a, b) => coverage(a) - coverage(b))[0];
  const inland =
    (action && byId(action.validation.source_plant)) ||
    plants.find((p) => p !== near);
  const stars = [
    [80, -20],
    [190, 30],
    [260, -60],
    [410, 60],
    [520, -30],
    [640, 40],
    [720, -64],
    [860, 4],
    [940, 52],
    [1020, -40],
    [1110, 24],
    [1170, -70],
    [350, 96],
    [590, 84],
  ];

  return (
    <svg
      className={`harbour ${running ? "running" : ""} ${item?.status || "idle"}`}
      viewBox={`0 ${-SKY} ${W} ${H + SKY}`}
      preserveAspectRatio="xMaxYMax slice"
      aria-hidden="true"
      focusable="false"
    >
      {/* sky in flat bands, a dusk glow on the horizon */}
      <rect y={-SKY} width={W} height={H + SKY} fill={ink.sky[0]} />
      <rect y={110} width={W} height={60} fill={ink.sky[1]} />
      <rect y={170} width={W} height={38} fill={ink.sky[2]} />
      <rect y={208} width={W} height={22} fill={ink.sky[3]} />
      <rect y={226} width={W} height={10} fill={ink.glow} opacity={0.55} />
      {stars.map(([x, y], i) => (
        <circle
          key={i}
          className="star"
          cx={x}
          cy={y}
          r={i % 3 ? 1.2 : 1.8}
          fill={ink.white}
          style={{ "--d": `${(i * 0.7) % 4}s` } as CSSProperties}
        />
      ))}
      <circle cx={980} cy={-30} r={18} fill="#f3ead2" />
      <circle cx={988} cy={-36} r={16} fill={ink.sky[0]} />

      {/* the far shore */}
      <path
        d="M0 236 V218 h40 v-8 h30 v12 h46 v-16 h22 v16 h60 v-6 h50 v10 h70 v-12 h24 v12 h90 v-8 h40 v8 h120 V236 Z"
        fill={ink.distant}
      />

      {/* sea */}
      <rect y={SEA} x={0} width={W} height={H - SEA} fill={ink.sea} />
      <rect y={300} x={0} width={W} height={40} fill={ink.seaDeep} />
      {[250, 266, 282, 298, 314, 328].map((y, i) => (
        <line
          key={y}
          className="ripple"
          x1={830}
          x2={W}
          y1={y}
          y2={y}
          stroke={ink.ripple}
          strokeWidth={2}
          strokeDasharray={`${18 + i * 4} ${46 + i * 9}`}
          style={{ "--d": `${3 + i}s` } as CSSProperties}
        />
      ))}

      {/* lighthouse on the breakwater, its beam sweeping */}
      <g transform="translate(1168 236)">
        <path d="M-30 0 H30 L22 -6 H-22 Z" fill={ink.land} />
        <path d="M-6 -6 L-4 -44 H4 L6 -6 Z" fill={ink.white} />
        <rect x={-5} y={-30} width={10} height={6} fill={ink.red} />
        <rect x={-6} y={-52} width={12} height={8} fill={ink.lit} />
        <path
          className="beam"
          d="M0 -48 L-240 -70 L-240 -30 Z"
          fill={ink.lit}
          opacity={0.07}
        />
      </g>

      {/* congestion: vessels queued off the port */}
      {congestion &&
        [900, 1000, 1080].map((x, i) => (
          <g
            key={x}
            className="queued"
            transform={`translate(${x} ${244 + i * 2}) scale(${0.32 + i * 0.04})`}
          >
            <path d="M0 -26 H232 L214 6 H18 Z" fill={ink.dark} />
            <rect
              x={30}
              y={-50}
              width={150}
              height={23}
              fill={[ink.red, ink.blue, ink.yellow][i]}
            />
            <rect x={190} y={-74} width={34} height={48} fill={ink.white} />
          </g>
        ))}

      {/* land */}
      <path d={`M0 ${GROUND} H860 V${H} H0 Z`} fill={ink.land} />
      <rect x={0} y={GROUND} width={860} height={6} fill={ink.quay} />
      <rect x={846} y={GROUND} width={14} height={H - GROUND} fill={ink.quay} />

      {/* road between the plants, and the transfer on it */}
      <rect x={250} y={GROUND + 8} width={190} height={14} fill={ink.dark} />
      <line
        x1={252}
        x2={438}
        y1={GROUND + 15}
        y2={GROUND + 15}
        stroke="#5d6577"
        strokeWidth={1.5}
        strokeDasharray="8 8"
      />
      {proposed && (
        <path
          className="proposed-route"
          d={`M210 ${GROUND + 4} Q 345 ${GROUND - 40} 480 ${GROUND + 4}`}
          fill="none"
          stroke={ink.yellow}
          strokeWidth={2.5}
          strokeDasharray="7 6"
        />
      )}
      {action && (driving || proposed || delivered) && (
        <g
          className={`truck ${driving ? "driving" : delivered ? "delivered" : "waiting"}`}
          style={{ "--from": "232px", "--to": "390px" } as CSSProperties}
        >
          <Truck quantity={action.validation.quantity} />
        </g>
      )}

      {plants.length > 0 ? (
        <>
          {inland && (
            <Factory x={40} plant={inland} scale={scale} receiving={false} />
          )}
          {near && (
            <Factory
              x={470}
              plant={near}
              scale={scale}
              receiving={Boolean(action && (driving || delivered))}
            />
          )}
        </>
      ) : (
        <>
          <path
            d="M40 268 V206 l22 -14 v14 l22 -14 v14 l22 -14 v14 l22 -14 V268 Z"
            fill={ink.dark}
          />
          <path
            d="M470 268 V206 l22 -14 v14 l22 -14 v14 l22 -14 v14 l22 -14 V268 Z"
            fill={ink.dark}
          />
        </>
      )}

      {/* the port: customs house, signal tower, stacks and a gantry crane */}
      <g>
        <rect x={668} y={214} width={84} height={54} fill="#2e3646" />
        <path d="M662 216 L710 196 L758 216 Z" fill={ink.dark} />
        {[0, 1, 2].map((i) => (
          <rect
            key={i}
            className={`window ${customs && i === 1 ? "watch" : ""}`}
            x={678 + i * 24}
            y={230}
            width={14}
            height={12}
            fill={ink.lit}
          />
        ))}
        <text className="scene-sign" x={710} y={262} textAnchor="middle">
          CUSTOMS
        </text>
        <rect x={764} y={150} width={8} height={118} fill={ink.dark} />
        <rect x={758} y={140} width={20} height={14} fill={ink.dark} />
        <circle
          className="signal-lamp"
          cx={768}
          cy={147}
          r={4}
          fill={ink.lit}
        />
        <Containers
          x={780}
          y={GROUND}
          rows={[[ink.blue, ink.red], [ink.yellow, ink.white], [ink.red]]}
        />
        <g className="crane">
          <rect x={808} y={128} width={6} height={140} fill={ink.yellow} />
          <rect x={846} y={128} width={6} height={140} fill={ink.yellow} />
          <rect x={790} y={124} width={180} height={7} fill={ink.yellow} />
          <path
            d="M808 131 L846 160 M846 131 L808 160"
            stroke={ink.yellow}
            strokeWidth={3}
          />
          <g className="trolley">
            <rect x={920} y={131} width={16} height={8} fill={ink.dark} />
            <line
              x1={928}
              y1={139}
              x2={928}
              y2={196}
              stroke={ink.white}
              strokeWidth={1}
            />
            <rect x={918} y={196} width={20} height={6} fill={ink.white} />
          </g>
        </g>
        {item && (
          <text className="scene-label" x={668} y={GROUND + 26}>
            {item.shipment.port_of_discharge.toUpperCase()}
          </text>
        )}
      </g>

      {item && (
        <Vessel
          flags={flags}
          name={item.shipment.vessel || item.shipment_id}
          far={item.status === "needs_human_decision" || congestion}
          running={running}
        />
      )}
    </svg>
  );
}
