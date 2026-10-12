/// <reference types="node" />

import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  BACKEND_URL,
  FRONTEND_URL,
  BACKEND_PORT,
  FRONTEND_PORT,
  TOKEN,
} from "./e2e/settings";

// Playwright loads this file in the main process and again in every worker.
// ??= makes the folder once: the workers inherit the variable, and a plain =
// would give each of them a folder of its own.
process.env.ZAMLR_E2E_DIR ??= mkdtempSync(join(tmpdir(), "music-zamlr-e2e-"));
const runDir = process.env.ZAMLR_E2E_DIR;

export default defineConfig({
  testDir: "e2e",
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  use: {
    baseURL: FRONTEND_URL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],
  webServer: [
    {
      command: `python -m uvicorn main:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: "../backend",
      url: `${BACKEND_URL}/api/health`,
      // Never a running server: one on these ports would be a leftover or one
      // of the developer's, holding the wrong database.
      reuseExistingServer: false,
      // The token and the origin make every request take the desktop app's
      // path: a token header and a CORS preflight.
      env: {
        ZAMLR_DATABASE_PATH: join(runDir, "e2e.db"),
        ZAMLR_TOKEN: TOKEN,
        ZAMLR_ALLOWED_ORIGINS: FRONTEND_URL,
      },
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: FRONTEND_URL,
      reuseExistingServer: false,
    },
  ],
});
