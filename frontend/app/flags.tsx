import { useId, type CSSProperties, type ReactNode } from "react";

// International Code of Signals flags, drawn from their standard geometry.
// Every flag is 3:2 (60 x 40) except the pennants, which taper to the fly.
const R = "var(--signal-red)";
const Y = "var(--signal-yellow)";
const B = "var(--flag-blue)";
const K = "var(--flag-black)";
const W = "var(--flag-white)";

export type FlagCode =
  | "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H" | "I" | "J" | "K" | "L" | "M"
  | "N" | "O" | "P" | "Q" | "R" | "S" | "T" | "U" | "V" | "W" | "X" | "Y" | "Z"
  | "answer" | "1" | "2";

const rect = (x: number, y: number, w: number, h: number, fill: string) => (
  <rect key={`${x}-${y}-${w}-${h}-${fill}`} x={x} y={y} width={w} height={h} fill={fill} />
);
const poly = (points: string, fill: string) => (
  <polygon key={points} points={points} fill={fill} />
);
const stripes = (fills: string[], vertical: boolean) =>
  fills.map((fill, i) =>
    vertical
      ? rect((60 / fills.length) * i, 0, 60 / fills.length + 0.2, 40, fill)
      : rect(0, (40 / fills.length) * i, 60, 40 / fills.length + 0.2, fill),
  );
const saltire = (fill: string, ground: string) => [
  rect(0, 0, 60, 40, ground),
  poly("0,0 7,0 60,35 60,40 53,40 0,5", fill),
  poly("60,0 60,5 7,40 0,40 0,35 53,0", fill),
];
const cross = (fill: string, ground: string) => [
  rect(0, 0, 60, 40, ground),
  rect(25, 0, 10, 40, fill),
  rect(0, 15, 60, 10, fill),
];

const drawings: Record<FlagCode, ReactNode> = {
  A: [rect(0, 0, 30, 40, W), poly("30,0 60,0 45,20 60,40 30,40", B)],
  B: [poly("0,0 60,0 45,20 60,40 0,40", R)],
  C: stripes([B, W, R, W, B], false),
  D: [rect(0, 0, 60, 40, Y), rect(0, 10, 60, 20, B)],
  E: [rect(0, 0, 60, 20, B), rect(0, 20, 60, 20, R)],
  F: [rect(0, 0, 60, 40, W), poly("30,0 60,20 30,40 0,20", R)],
  G: stripes([Y, B, Y, B, Y, B], true),
  H: [rect(0, 0, 30, 40, W), rect(30, 0, 30, 40, R)],
  I: [rect(0, 0, 60, 40, Y), <circle key="c" cx={30} cy={20} r={10} fill={K} />],
  J: stripes([B, W, B], false),
  K: [rect(0, 0, 30, 40, Y), rect(30, 0, 30, 40, B)],
  L: [
    rect(0, 0, 30, 20, Y),
    rect(30, 0, 30, 20, K),
    rect(0, 20, 30, 20, K),
    rect(30, 20, 30, 20, Y),
  ],
  M: saltire(W, B),
  N: Array.from({ length: 16 }, (_, i) =>
    rect((i % 4) * 15, Math.floor(i / 4) * 10, 15.2, 10.2,
      (i % 4) % 2 === Math.floor(i / 4) % 2 ? B : W),
  ),
  O: [poly("0,0 0,40 60,40", Y), poly("0,0 60,0 60,40", R)],
  P: [rect(0, 0, 60, 40, B), rect(20, 13.3, 20, 13.4, W)],
  Q: [rect(0, 0, 60, 40, Y)],
  R: cross(Y, R),
  S: [rect(0, 0, 60, 40, W), rect(20, 13.3, 20, 13.4, B)],
  T: stripes([R, W, B], true),
  U: [
    rect(0, 0, 30, 20, R),
    rect(30, 0, 30, 20, W),
    rect(0, 20, 30, 20, W),
    rect(30, 20, 30, 20, R),
  ],
  V: saltire(R, W),
  W: [rect(0, 0, 60, 40, B), rect(8, 8, 44, 24, W), rect(18, 14, 24, 12, R)],
  X: cross(B, W),
  Y: [
    rect(0, 0, 60, 40, Y),
    ...[-40, -20, 0, 20, 40].map((o) =>
      poly(`${o},40 ${o + 10},40 ${o + 50},0 ${o + 40},0`, R),
    ),
  ],
  Z: [
    poly("0,0 60,0 30,20", Y),
    poly("0,0 30,20 0,40", K),
    poly("0,40 30,20 60,40", R),
    poly("60,0 60,40 30,20", B),
  ],
  answer: stripes([R, W, R, W, R], true),
  "1": [rect(0, 0, 60, 40, W), <circle key="c" cx={18} cy={20} r={8} fill={R} />],
  "2": [rect(0, 0, 60, 40, B), <circle key="c" cx={18} cy={20} r={8} fill={W} />],
};

// What each flag says, in the words of the International Code of Signals.
export const flagMeaning: Partial<Record<FlagCode, string>> = {
  answer: "Signal received",
  C: "Affirmative",
  K: "I wish to communicate with you",
  N: "Negative",
  P: "About to proceed",
  Q: "Requesting clearance to enter port",
  V: "I require assistance",
};

const pennants = new Set<FlagCode>(["answer", "1", "2"]);

export function Flag({
  code,
  height = 20,
  label,
  className = "",
}: {
  code: FlagCode;
  height?: number;
  label?: string;
  className?: string;
}) {
  const pennant = pennants.has(code);
  const width = pennant ? height * 1.8 : height * 1.5;
  const id = `pennant${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <svg
      className={`flag ${pennant ? "pennant" : ""} ${className}`}
      viewBox="0 0 60 40"
      preserveAspectRatio="none"
      width={width}
      height={height}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      {pennant && (
        <defs>
          <clipPath id={id}>
            <polygon points="0,0 60,14 60,26 0,40" />
          </clipPath>
        </defs>
      )}
      <g clipPath={pennant ? `url(#${id})` : undefined}>{drawings[code]}</g>
      {pennant && (
        <polygon
          points="0.5,0.5 59.5,14 59.5,26 0.5,39.5"
          fill="none"
          stroke="rgb(21 23 28 / 0.3)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}

// The bare cloth in flag units (60 x 40), for drawing a flag inside a scene.
export function FlagShape({ code }: { code: FlagCode }) {
  const id = `pennant${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  if (!pennants.has(code)) return <g>{drawings[code]}</g>;
  return (
    <g>
      <defs>
        <clipPath id={id}>
          <polygon points="0,0 60,14 60,26 0,40" />
        </clipPath>
      </defs>
      <g clipPath={`url(#${id})`}>{drawings[code]}</g>
    </g>
  );
}

// A flag on its halyard. A new code remounts it, so it runs up and unfurls;
// while `flying` it is cut into slices of cloth that wave out of phase.
const SLICES = 8;
export function Hoist({
  code,
  height = 40,
  flying = false,
  label,
}: {
  code: FlagCode;
  height?: number;
  flying?: boolean;
  label?: string;
}) {
  const pennant = pennants.has(code);
  const width = pennant ? height * 1.8 : height * 1.5;
  return (
    <span
      className="hoist"
      data-flying={flying}
      style={{ "--flag-w": `${width}px`, "--flag-h": `${height}px` } as CSSProperties}
      role="img"
      aria-label={label}
    >
      <span className="hoist-cloth" key={code}>
        {flying ? (
          Array.from({ length: SLICES }, (_, i) => (
            <span
              className="hoist-slice"
              key={i}
              style={{ "--i": i, "--n": SLICES } as CSSProperties}
            >
              <Flag code={code} height={height} />
            </span>
          ))
        ) : (
          <Flag code={code} height={height} />
        )}
      </span>
    </span>
  );
}

// Each actor in the log signs with the flag of its initial; the event feed
// flies the answering pennant, since an event is a signal received.
export function actorFlag(actor: string): FlagCode {
  if (actor === "Event feed") return "answer";
  const letter = actor.trim().charAt(0).toUpperCase();
  return /^[A-Z]$/.test(letter) ? (letter as FlagCode) : "answer";
}
