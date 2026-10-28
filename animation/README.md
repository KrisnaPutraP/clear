# CLEAR motion assets

The same authoring approach as the portfolio's `animation/src/CafeNight`: deterministic Remotion frames, code-drawn geometry, and a lighting pass. The compass uses a bevelled 3D ring and an extruded needle based on CLEAR's original Compass icon. Visible surfaces are projected into SVG and sorted by depth every frame. There are no raster images, AI-generated images, or CSS discs pretending to be a solid.

```sh
npm install
npm run dev       # Scrub ClearCompass in Remotion Studio
npm run preview   # Render one preview with Remotion
npm run assets    # Export the vector assets
npm run webp      # Pack the loading SVG into the animated WebP the app shows
```

The scene is `src/compass.mjs`. The SVG runs at 60 fps in a four-second loop: three revolutions that start slowly, accelerate sharply, then settle onto the starting pose. Reused vector poses keep the export small. Both the SVG and the Remotion scene have transparent backgrounds. The frontend serves a static 3D frame for reduced motion, and the original outline mark in the sidebar. Remotion is an authoring dependency only.

The app shows the loading compass as `clear-compass-loading.webp`, rendered from the SVG frame by frame (`render-webp.mjs`, which needs the frontend's Playwright and an ffmpeg with libwebp). A browser redraws the SVG's 240 SMIL frames on the main thread for every copy on screen; with four copies while agents ran, the workspace dropped to about 18 fps. The WebP carries the same frames and keeps it at 60. Run `npm run webp` after `npm run assets` whenever the scene changes.
