# CLEAR motion assets

The same authoring approach as the portfolio's `animation/src/CafeNight`: deterministic Remotion frames, code-drawn geometry, and a lighting pass. The compass uses a bevelled 3D ring and an extruded needle based on CLEAR's original Compass icon. Visible surfaces are projected into SVG and sorted by depth every frame. There are no raster images, AI-generated images, or CSS discs pretending to be a solid.

```sh
npm install
npm run dev       # Scrub ClearCompass in Remotion Studio
npm run preview   # Render one preview with Remotion
npm run assets    # Export the vector assets used by the app
```

The scene is `src/compass.mjs`. The SVG runs at 60 fps in a four-second loop: three revolutions that start slowly, accelerate sharply, then settle onto the starting pose. Reused vector poses keep the export small. Both the SVG and the Remotion scene have transparent backgrounds. The frontend serves a static 3D frame for reduced motion, and the original outline mark in the sidebar. Remotion is an authoring dependency only; the app uses ordinary SVG image assets.
