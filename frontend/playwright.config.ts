import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  BACKEND_URL,
  FRONTEND_URL,
  BACKEND_PORT,
  FRONTEND_PORT,
  NO_FPCALC_PORT,
  NO_FPCALC_URL,
  TOKEN,
} from "./e2e/settings";

const RUN_DIR_PREFIX = "music-zamlr-e2e-";

// Playwright loads this file in the main process and again in every worker.
// Only the first load, in the main process, finds the variable unset, so the
// folder is made once and the workers inherit it.
if (process.env.ZAMLR_E2E_DIR === undefined) {
  // Earlier runs' folders go first, each holding a database. They are removed
  // here and not at the end of a run, because the backends still hold their
  // databases open while Playwright's teardown runs. Removing them cannot
  // reach a run in progress: the ports are fixed, so a second run cannot
  // start beside one. A folder that cannot be removed is left for next time.
  for (const name of readdirSync(tmpdir())) {
    if (name.startsWith(RUN_DIR_PREFIX)) {
      try {
        rmSync(join(tmpdir(), name), { recursive: true, force: true });
      } catch {
        // Locked or not ours to remove; the next run tries again.
      }
    }
  }
  process.env.ZAMLR_E2E_DIR = mkdtempSync(join(tmpdir(), RUN_DIR_PREFIX));
}
const runDir = process.env.ZAMLR_E2E_DIR;

export default defineConfig({
  testDir: "e2e",
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  // In CI, an HTML report as well, which the workflow keeps when a run fails:
  // a trace there is the only way to see what the browser saw. Never opened
  // here, because opening it would hold the terminal.
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
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
      command: `python -m uvicorn main:app --host 127.0.0.1 --port ${NO_FPCALC_PORT}`,
      cwd: "../backend",
      url: `${NO_FPCALC_URL}/api/health`,
      reuseExistingServer: false,
      env: {
        ZAMLR_DATABASE_PATH: join(runDir, "no-fpcalc.db"),
        ZAMLR_TOKEN: TOKEN,
        ZAMLR_ALLOWED_ORIGINS: FRONTEND_URL,
        // A path that does not exist. Set, it is the only place the backend
        // looks: it does not fall back to fpcalc on PATH.
        ZAMLR_FPCALC: join(runDir, "no-such-fpcalc"),
      },
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: FRONTEND_URL,
      reuseExistingServer: false,
    },
  ],
});
