import { expect, test } from "./fixtures";
import { BACKEND_URL, TOKEN } from "./settings";

test("shows the splash until the backend answers", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/health", async (route) => {
    await gate;
    // A request the page has already given up on cannot be continued, and
    // Playwright would throw here for a reason that is not the app's.
    await route.continue().catch(() => {});
  });
  const asked: string[] = [];
  page.on("request", (request) => asked.push(request.url()));

  await page.goto("/");

  // All of this happens while the first health check is held, and well
  // inside the two seconds after which the page abandons it and asks again.
  await expect(page.getByText("Starting the backend…")).toBeVisible();
  await expect(page.getByRole("tab")).toHaveCount(0);
  // No view may ask the backend anything before it has answered: one cause
  // would otherwise produce two error messages.
  expect(
    asked.filter(
      (url) =>
        url.includes("/api/collections") ||
        url.includes("/api/settings/format-order"),
    ),
  ).toEqual([]);

  release();

  await expect(page.getByRole("tab", { name: "Collections" })).toBeVisible();
});

test.describe("when no backend answers", () => {
  // Doubled backslashes: in a TypeScript string "\l" is no escape, and the
  // backslash would silently disappear.
  const LOG_PATH = "C:\\logs\\backend.log";

  test.use({
    zamlr: { apiBase: BACKEND_URL, token: TOKEN, logPath: LOG_PATH },
    // Each refused health check is reported by the browser itself.
    allowedConsoleErrors: [/Failed to load resource/],
  });

  test("gives up and names the log file", async ({ page }) => {
    // The page waits about fifteen seconds before it gives up.
    test.setTimeout(60_000);
    await page.route("**/api/health", (route) =>
      route.abort("connectionrefused"),
    );

    await page.goto("/");

    await expect(page.getByRole("alert")).toHaveCount(1, { timeout: 30_000 });
    // The whole sentence, because it is built from three pieces: only the
    // exact text proves the space at each join.
    await expect(page.getByRole("alert")).toHaveText(
      `The backend did not answer at ${BACKEND_URL} within 15 seconds. ` +
        `Close the app and open it again. ` +
        `The log file at ${LOG_PATH} holds the reason.`,
    );
    await expect(page.getByText(`Log file: ${LOG_PATH}`)).toBeVisible();
    // The button opens a folder on the machine that runs the shell, so a
    // browser must not offer it.
    await expect(page.getByRole("button", { name: "Open folder" })).toHaveCount(
      0,
    );
    await expect(page.getByRole("tab")).toHaveCount(0);
  });
});
