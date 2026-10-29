import type { CSSProperties } from "react";

// The night over the whole workspace: the same stars as the harbour scene,
// sparse and dim, so the page and the drawing share one sky. Positions come
// from a fixed seed, so the server and the browser draw the same sky.
const W = 1440;
const H = 900;

function seeded(seed: number) {
  return () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
}

const random = seeded(20261028);
const stars = Array.from({ length: 90 }, (_, i) => ({
  x: random() * W,
  y: random() * H,
  r: i % 7 === 0 ? 1.5 : 0.9,
  opacity: 0.2 + random() * 0.35,
  delay: random() * 6,
}));

export function Sky() {
  return (
    <svg
      className="night-sky"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      {stars.map((star, i) => (
        <circle
          key={i}
          className="star"
          cx={star.x.toFixed(1)}
          cy={star.y.toFixed(1)}
          r={star.r}
          fill="#ffffff"
          opacity={star.opacity.toFixed(2)}
          style={{ "--d": `${star.delay.toFixed(2)}s` } as CSSProperties}
        />
      ))}
    </svg>
  );
}
