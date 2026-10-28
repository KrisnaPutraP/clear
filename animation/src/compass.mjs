import { Easing, interpolate } from "remotion";

// Like the portfolio's CafeNight scene: geometry, light and frame timing are
// authored in code. Project the solid into SVG instead of baking a raster clip.
export const FPS = 60;
export const FRAMES = 240;
const spinEase = Easing.bezier(0.76, 0, 0.24, 1);
const TAU = Math.PI * 2;
const SEGMENTS = 64;
const faces = [];
const jade = [31, 112, 83];
const mint = [134, 194, 164];
const porcelain = [220, 238, 224];
const add = (points, color) =>
  faces.push({ points: [...points].reverse(), color });
const polar = (r, angle, z) => [r * Math.cos(angle), r * Math.sin(angle), z];

// A continuous bevelled annulus, with a genuinely open centre.
const profile = [
  [43.2, -3.6],
  [44.5, -2.3],
  [44.5, 2.3],
  [43.2, 3.6],
  [39.5, 3.6],
  [38.4, 2.5],
  [38.4, -2.5],
  [39.5, -3.6],
];
for (let i = 0; i < SEGMENTS; i++) {
  const a = (i / SEGMENTS) * TAU;
  const b = ((i + 1) / SEGMENTS) * TAU;
  for (let j = 0; j < profile.length; j++) {
    const [r1, z1] = profile[j];
    const [r2, z2] = profile[(j + 1) % profile.length];
    add(
      [polar(r1, a, z1), polar(r2, a, z2), polar(r2, b, z2), polar(r1, b, z1)],
      j === 2 || j === 4 ? mint : jade,
    );
  }
}

// The same northeast-pointing needle as CLEAR's original Compass mark.
// Two raised triangular facets sit above a solid four-sided extrusion.
const needle = [
  [22, -22],
  [8, 8],
  [-22, 22],
  [-8, -8],
];
for (let i = 0; i < needle.length; i++) {
  const a = needle[i];
  const b = needle[(i + 1) % needle.length];
  add(
    [
      [...a, -2.8],
      [...a, 2.8],
      [...b, 2.8],
      [...b, -2.8],
    ],
    jade,
  );
  add(
    [
      [...a, 2.8],
      [0, 0, 5],
      [...b, 2.8],
    ],
    i < 2 ? mint : jade,
  );
  add(
    [
      [...b, -2.8],
      [0, 0, -4.5],
      [...a, -2.8],
    ],
    i < 2 ? jade : porcelain,
  );
}

const cross = (a, b) => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
const subtract = (a, b) => a.map((v, i) => v - b[i]);
const normalize = (v) => {
  const length = Math.hypot(...v);
  return v.map((n) => n / length);
};
const light = normalize([-0.55, -0.8, 1.5]);
const round = (n) => Number(n.toFixed(1));

export function turnsAtFrame(frame) {
  return interpolate(frame, [0, FRAMES], [0, 3], { easing: spinEase });
}

export function framePaths(frame) {
  // Reusable three-degree poses keep the vector asset small while the timeline
  // accelerates through three revolutions and settles back onto its first pose.
  const turn =
    ((Math.round(turnsAtFrame(frame) * 120) % 120) / 120) * TAU - 0.36;
  const tilt = -0.25;
  const rotate = ([x, y, z]) => {
    const u = x * Math.cos(turn) + z * Math.sin(turn);
    const w = -x * Math.sin(turn) + z * Math.cos(turn);
    return [
      u,
      y * Math.cos(tilt) - w * Math.sin(tilt),
      y * Math.sin(tilt) + w * Math.cos(tilt),
    ];
  };
  const visible = faces
    .flatMap(({ points, color }) => {
      const p = points.map(rotate);
      const normal = normalize(
        cross(subtract(p[1], p[0]), subtract(p[2], p[0])),
      );
      if (normal[2] <= 0.001) return [];
      const diffuse = Math.max(
        0,
        normal.reduce((sum, v, i) => sum + v * light[i], 0),
      );
      const specular =
        Math.pow(
          Math.max(0, normal[2] * 0.84 - normal[0] * 0.28 - normal[1] * 0.46),
          24,
        ) * 0.28;
      const fill =
        "#" +
        color
          .map((c) =>
            Math.min(
              255,
              Math.round(c * (0.48 + diffuse * 0.58) + 255 * specular),
            )
              .toString(16)
              .padStart(2, "0"),
          )
          .join("");
      const d =
        p
          .map(([x, y, z], i) => {
            const perspective = 320 / (320 - z);
            return `${i === 0 ? "M" : "L"}${round(64 + x * perspective)} ${round(64 + y * perspective)}`;
          })
          .join("") + "Z";
      return [{ d, fill, z: p.reduce((sum, v) => sum + v[2], 0) / p.length }];
    })
    .sort((a, b) => a.z - b.z);
  // Matching subpixel strokes close seams between adjacent lit facets.
  const paths = [];
  for (const face of visible) {
    const last = paths.at(-1);
    if (last?.fill === face.fill) last.d += face.d;
    else paths.push({ ...face });
  }
  return paths
    .map(({ d, fill }) => `<path d="${d}" fill="${fill}" stroke="${fill}"/>`)
    .join("");
}

export function frameSvg(frame) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="384" height="384" viewBox="0 0 128 128" stroke-width=".3" stroke-linejoin="round"><title>CLEAR compass</title>${framePaths(frame)}</svg>`;
}
