import { defineConfig } from "@playwright/test";
import path from "node:path";

const python = path.resolve(
  "..",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const apiPort = process.env.CLEAR_E2E_API_PORT || "8101";
const webPort = process.env.CLEAR_E2E_WEB_PORT || "3101";

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn clear_app.api:create_app --factory --host 127.0.0.1 --port ${apiPort}`,
      url: `http://127.0.0.1:${apiPort}/health`,
      reuseExistingServer: false,
      env: {
        CLEAR_UI_SCRIPTED: "1",
        CLEAR_RUNTIME_DIR: path.resolve(".test-runtime", String(Date.now())),
        CLEAR_PREDICTION_BACKEND: "baseline",
      },
    },
    {
      command: `npm run dev -- --port ${webPort}`,
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: false,
      env: {
        CLEAR_API_URL: `http://127.0.0.1:${apiPort}`,
        CLEAR_NEXT_DIST_DIR: ".next-e2e",
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
