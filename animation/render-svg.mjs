import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import {
  FPS,
  FRAMES,
  framePaths,
  frameSvg,
  turnsAtFrame,
} from "./src/compass.mjs";

const out = new URL("../frontend/public/", import.meta.url);
await mkdir(out, { recursive: true });
// The static brand preserves the original Lucide Compass silhouette.
const mark =
  '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 24 24" fill="none" stroke="#1C4597" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><title>CLEAR compass</title><circle cx="12" cy="12" r="10"/><path d="M16.24 7.76 14.12 14.12 9.88 9.88Z" fill="#D0231B" stroke="#D0231B"/><path d="M7.76 16.24 9.88 9.88 14.12 14.12Z" fill="#22252C" stroke="#22252C"/></svg>';
await writeFile(new URL("clear-compass.svg", out), mark + "\n");
await writeFile(new URL("clear-compass-still.svg", out), frameSvg(0) + "\n");

// A single vector animation, not a movie or an embedded bitmap. Frames are
// depth-sorted and lit using the exact scene shown in Remotion Studio.
const duration = FRAMES / FPS;
const poses = new Map();
const frames = Array.from({ length: FRAMES }, (_, i) => {
  const paths = framePaths(i);
  assert(
    paths.length > 0 && !/NaN|Infinity/.test(paths),
    `Invalid geometry at frame ${i}`,
  );
  if (!poses.has(paths)) poses.set(paths, `pose-${poses.size}`);
  const pose = poses.get(paths);
  const start = i / FRAMES;
  const end = (i + 1) / FRAMES;
  const values = i === 0 ? "1;0;0" : i === FRAMES - 1 ? "0;1;0" : "0;1;0;0";
  const times =
    i === 0
      ? `0;${end};1`
      : i === FRAMES - 1
        ? `0;${start};1`
        : `0;${start};${end};1`;
  return `<g opacity="${i === 0 ? 1 : 0}"><animate attributeName="opacity" values="${values}" keyTimes="${times}" calcMode="discrete" dur="${duration}s" repeatCount="indefinite"/><use href="#${pose}"/></g>`;
}).join("");
const definitions = [...poses]
  .map(([paths, id]) => `<g id="${id}">${paths}</g>`)
  .join("");
assert.equal(
  framePaths(0),
  framePaths(FRAMES),
  "Rotation must loop seamlessly",
);
const speed = (frame) => turnsAtFrame(frame + 1) - turnsAtFrame(frame);
assert(
  speed(FRAMES / 2) > speed(FPS / 2) * 15,
  "Spin must accelerate noticeably",
);
assert(
  speed(FRAMES / 2) > speed(FRAMES - FPS / 2) * 15,
  "Spin must settle before repeating",
);
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="384" height="384" viewBox="0 0 128 128" stroke-width=".3" stroke-linejoin="round"><title>CLEAR compass rotating in three dimensions</title><defs>${definitions}</defs>${frames}</svg>\n`;
await writeFile(new URL("clear-compass-loading.svg", out), svg);
console.log(
  `Exported ${FRAMES} vector frames at ${FPS} fps to ${fileURLToPath(out)} (${Math.round(svg.length / 1024)} KB uncompressed)`,
);
