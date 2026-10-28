import React from "react";
import {
  AbsoluteFill,
  Composition,
  registerRoot,
  useCurrentFrame,
} from "remotion";
import { FPS, FRAMES, frameSvg } from "./compass.mjs";

function Compass() {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{ background: "#f5f7f3" }}
      dangerouslySetInnerHTML={{ __html: frameSvg(frame) }}
    />
  );
}

function Root() {
  return (
    <Composition
      id="ClearCompass"
      component={Compass}
      durationInFrames={FRAMES}
      fps={FPS}
      width={384}
      height={384}
    />
  );
}

registerRoot(Root);
