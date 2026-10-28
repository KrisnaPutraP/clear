# CLEAR motion assets

The same authoring approach as the portfolio's `animation/src/CafeNight`: deterministic Remotion frames, code-drawn geometry, and a lighting pass. The compass uses a bevelled 3D ring and an extruded needle based on CLEAR's original Compass icon. Visible surfaces are projected into SVG and sorted by depth every frame. There are no raster images, AI-generated images, or CSS discs pretending to be a solid.

```sh
npm install
npm run dev       # Scrub ClearCompass in Remotion Studio
npm run preview   # Render one preview with Remotion
npm run assets    # Export the vector assets used by the app
```

The scene is `src/compass.mjs`. The exported SVG animation is 72 frames at 24 fps with a seamless three-second loop. The frontend serves a static 3D frame for reduced motion, and the original outline mark in the sidebar. Remotion is an authoring dependency only; the app uses ordinary SVG image assets.
