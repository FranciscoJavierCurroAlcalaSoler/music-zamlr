import { expect, test as base } from "@playwright/test";
import { BACKEND_URL, TOKEN } from "./settings";

export const test = base.extend({
  page: async ({ page }, use) => {
    // What the desktop shell injects, set before any script of the page runs.
    // The values go in as an argument because the function runs in the
    // browser and cannot see this module. __TAURI_INTERNALS__ stays unset:
    // with it, the page would call Tauri plugins that a browser lacks.
    await page.addInitScript(
      (injected) => {
        (globalThis as { __ZAMLR__?: unknown }).__ZAMLR__ = injected;
      },
      { apiBase: BACKEND_URL, token: TOKEN },
    );

    await use(page);
  },
});

export { expect };
