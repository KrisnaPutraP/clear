import { defineConfig } from "@playwright/test";
import path from "node:path";

const python = path.resolve(
  "..",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  use: {
    baseURL: "http://127.0.0.1:3100",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn clear_app.api:create_app --factory --host 127.0.0.1 --port 8100`,
      url: "http://127.0.0.1:8100/health",
      reuseExistingServer: false,
      env: {
        CLEAR_UI_SCRIPTED: "1",
        CLEAR_RUNTIME_DIR: path.resolve(".test-runtime", String(Date.now())),
        CLEAR_PREDICTION_BACKEND: "baseline",
      },
    },
    {
      command: "npm run dev -- --port 3100",
      url: "http://127.0.0.1:3100",
      reuseExistingServer: false,
      env: {
        CLEAR_API_URL: "http://127.0.0.1:8100",
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
