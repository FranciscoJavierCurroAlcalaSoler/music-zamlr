import { expect, test as base } from "@playwright/test";
import { BACKEND_URL, TOKEN } from "./settings";

/** What the desktop shell injects as __ZAMLR__. */
export type Injected = { apiBase: string; token: string; logPath?: string };

export const test = base.extend<{
  zamlr: Injected;
  allowedConsoleErrors: RegExp[];
}>({
  zamlr: [{ apiBase: BACKEND_URL, token: TOKEN }, { option: true }],
  // Errors a spec expects, such as the browser's report of a request that a
  // test refused on purpose. Everything else the page logs as an error fails
  // the test.
  allowedConsoleErrors: [[], { option: true }],

  page: async ({ page, zamlr, allowedConsoleErrors }, use) => {
    // What the desktop shell injects, set before any script of the page runs.
    // The values go in as an argument because the function runs in the
    // browser and cannot see this module. __TAURI_INTERNALS__ stays unset:
    // with it, the page would call Tauri plugins that a browser lacks.
    await page.addInitScript((injected) => {
      (globalThis as { __ZAMLR__?: unknown }).__ZAMLR__ = injected;
    }, zamlr);

    // React and MUI report misuse through console.error, and an uncaught
    // exception arrives as pageerror. No other suite runs the components, so
    // this is the only place either can be seen. The listeners go on before
    // the test runs, so that nothing logged while the page loads is missed.
    const errors: string[] = [];
    const record = (text: string) => {
      if (!allowedConsoleErrors.some((pattern) => pattern.test(text))) {
        errors.push(text);
      }
    };
    page.on("console", (message) => {
      if (message.type() === "error") record(message.text());
    });
    page.on("pageerror", (error) => record(error.message));

    await use(page);

    expect(errors, "errors the page logged").toEqual([]);
  },
});

export { expect };
