// Renders the vector compass (clear-compass-loading.svg) frame by frame and
// packs the frames into an animated WebP. The app shows the WebP: browsers
// redraw the SVG's 240 SMIL frames on the main thread for every copy on the
// page, which held the workspace near 18 fps while agents ran; the WebP keeps
// the same frames at 60 fps for almost no cost.
//
// Needs the frontend's Playwright (npm install in ../frontend) and an ffmpeg
// with libwebp on the PATH, or its path in FFMPEG.
import { execFileSync } from "node:child_process";
import { mkdir, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { FPS, FRAMES } from "./src/compass.mjs";

const { chromium } = await import("../frontend/node_modules/playwright/index.mjs");

const SIZE = 192; // Twice the largest size the app shows it at.
const publicDir = new URL("../frontend/public/", import.meta.url);
const framesDir = new URL("out/compass-frames/", import.meta.url);
await rm(framesDir, { recursive: true, force: true });
await mkdir(framesDir, { recursive: true });

const svg = (await readFile(new URL("clear-compass-loading.svg", publicDir), "utf8"))
  .replace('width="384" height="384"', `width="${SIZE}" height="${SIZE}"`);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: SIZE, height: SIZE } });
await page.setContent(`<body style="margin:0;background:transparent">${svg}</body>`);
await page.evaluate(() => document.querySelector("svg").pauseAnimations());
for (let i = 0; i < FRAMES; i++) {
  await page.evaluate((t) => document.querySelector("svg").setCurrentTime(t), i / FPS);
  await page.screenshot({
    path: fileURLToPath(new URL(`f${String(i).padStart(3, "0")}.png`, framesDir)),
    omitBackground: true,
    clip: { x: 0, y: 0, width: SIZE, height: SIZE },
  });
}
await browser.close();

const target = fileURLToPath(new URL("clear-compass-loading.webp", publicDir));
execFileSync(process.env.FFMPEG || "ffmpeg", [
  "-y", "-loglevel", "error",
  "-framerate", String(FPS),
  "-i", join(fileURLToPath(framesDir), "f%03d.png"),
  "-c:v", "libwebp_anim", "-lossless", "0", "-q:v", "82", "-loop", "0",
  target,
]);
console.log(`Exported ${FRAMES} frames at ${FPS} fps to ${target}`);
