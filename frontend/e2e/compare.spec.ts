import { existsSync, mkdirSync, readdirSync } from "node:fs";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";
import {
  INCOMING_FILES,
  MAIN_FILES,
  addCollection,
  choose,
  compare,
  musicFolder,
  uniqueName,
} from "./library";
import { BACKEND_URL, NO_FPCALC_URL, TOKEN } from "./settings";

const FPCALC_WARNING = "fpcalc was not found";

/**
 * The banner over an old comparison, found by the sentence it always ends
 * with. Its whole text is compared, because a cause that should be absent can
 * only be proved absent there: the unreadable-files warning and the hidden
 * Collections tab both show paths, and a test's output folder is named after
 * the test's title.
 */
function oldComparisonBanner(page: Page) {
  return page.getByRole("alert").filter({ hasText: "Run Compare again" });
}

/** Make the main and the incoming collection, and return their names. */
async function twoCollections(
  request: Parameters<typeof addCollection>[0],
  testInfo: Parameters<typeof musicFolder>[0],
  backendUrl: string = BACKEND_URL,
) {
  const main = uniqueName(testInfo, "Main");
  const incoming = uniqueName(testInfo, "Incoming");
  await addCollection(
    request,
    main,
    musicFolder(testInfo, "main", MAIN_FILES),
    backendUrl,
  );
  await addCollection(
    request,
    incoming,
    musicFolder(testInfo, "incoming", INCOMING_FILES),
    backendUrl,
  );
  return { main, incoming };
}

test("compares two collections and shows the counts", async ({
  page,
  request,
}, testInfo) => {
  const { main, incoming } = await twoCollections(request, testInfo);
  await page.goto("/");

  await compare(page, main, incoming);

  await expect(
    page.getByRole("tab", { name: "Import candidates (3)" }),
  ).toBeVisible();
  await expect(
    page.getByRole("tab", { name: "Only in main (1)" }),
  ).toBeVisible();
  for (const name of [
    "All (3)",
    "Missing (1)",
    "Upgrades (1)",
    "Already have (1)",
    "Needs review (0)",
  ]) {
    await expect(page.getByRole("button", { name })).toBeVisible();
  }
  // The values the API sends as numbers, as the table formats them.
  const upgrade = page.getByRole("row").filter({ hasText: "Upgrade" });
  await expect(upgrade).toContainText("Test Track AAC");
  await expect(upgrade).toContainText("217 kbps");
  await expect(upgrade).toContainText("0:01");
  await expect(upgrade).toContainText("125 kbps");
  await expect(
    page.getByRole("alert").filter({ hasText: "could not be read" }),
  ).toContainText(
    "2 files could not be read, so their tracks were compared by tags only.",
  );
  await expect(page.getByText(FPCALC_WARNING)).toHaveCount(0);
});

test("keeps the selection across a tab switch", async ({
  page,
  request,
}, testInfo) => {
  const { main, incoming } = await twoCollections(request, testInfo);
  await page.goto("/");
  await compare(page, main, incoming);
  const missing = page.getByRole("row").filter({ hasText: "Missing" });

  await missing.getByRole("checkbox").check();
  await expect(page.getByText("1 selected")).toBeVisible();

  // The outer tabs hide a view instead of removing it, which is what keeps
  // the selection.
  await page.getByRole("tab", { name: "Settings" }).click();
  await page.getByRole("tab", { name: "Compare" }).click();
  await expect(page.getByText("1 selected")).toBeVisible();
  await expect(missing.getByRole("checkbox")).toBeChecked();

  // The inner tab removes the table; the selection lives above it.
  await page.getByRole("tab", { name: /^Only in main/ }).click();
  await page.getByRole("tab", { name: /^Import candidates/ }).click();
  await expect(page.getByText("1 selected")).toBeVisible();
  await expect(missing.getByRole("checkbox")).toBeChecked();
});

test("cancelling the preview writes nothing", async ({
  page,
  request,
}, testInfo) => {
  const { main, incoming } = await twoCollections(request, testInfo);
  const destination = testInfo.outputPath("destination");
  mkdirSync(destination);
  await page.goto("/");
  await compare(page, main, incoming);
  await page
    .getByRole("row")
    .filter({ hasText: "Missing" })
    .getByRole("checkbox")
    .check();

  await page.getByLabel("Destination folder").fill(destination);
  await page.getByRole("button", { name: "Preview import" }).click();
  const dialog = page.getByRole("dialog", { name: "Confirm import" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("test_track.wma");
  await dialog.getByRole("button", { name: "Cancel" }).click();

  await expect(dialog).toHaveCount(0);
  expect(readdirSync(destination)).toEqual([]);
  await expect(page.getByText("1 selected")).toBeVisible();
});

test("a removed collection marks the comparison as old", async ({
  page,
  request,
}, testInfo) => {
  const { main, incoming } = await twoCollections(request, testInfo);
  await page.goto("/");
  await compare(page, main, incoming);

  await page.getByRole("tab", { name: "Collections" }).click();
  await page
    .getByRole("row")
    .filter({ hasText: incoming })
    .getByRole("button", { name: "Remove" })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Remove" })
    .click();
  await expect(page.getByRole("row").filter({ hasText: incoming })).toHaveCount(
    0,
  );
  await page.getByRole("tab", { name: "Compare" }).click();

  await expect(oldComparisonBanner(page)).toHaveText(
    "A collection in this comparison was removed. " +
      "Run Compare again for current results.",
  );
  await expect(
    page.getByRole("button", { name: "Preview import" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Compare", exact: true }),
  ).toBeDisabled();
  // The files stay where they are.
  expect(existsSync(testInfo.outputPath("incoming", INCOMING_FILES[0]))).toBe(
    true,
  );
});

test("choosing another collection is named as a new choice", async ({
  page,
  request,
}, testInfo) => {
  const { main, incoming } = await twoCollections(request, testInfo);
  const other = uniqueName(testInfo, "Other");
  await addCollection(
    request,
    other,
    musicFolder(testInfo, "other", INCOMING_FILES),
  );
  await page.goto("/");
  await compare(page, main, incoming);

  await choose(page, "Incoming collection", other);
  await expect(oldComparisonBanner(page)).toHaveText(
    "You chose different collections since this comparison. " +
      "Run Compare again for current results.",
  );

  // Back to the collection the table came from: nothing is old any more.
  await choose(page, "Incoming collection", incoming);
  await expect(oldComparisonBanner(page)).toHaveCount(0);
});

test.describe("against a backend without fpcalc", () => {
  test.use({ zamlr: { apiBase: NO_FPCALC_URL, token: TOKEN } });

  test("warns when fpcalc is missing", async ({ page, request }, testInfo) => {
    const { main, incoming } = await twoCollections(
      request,
      testInfo,
      NO_FPCALC_URL,
    );
    await page.goto("/");

    await compare(page, main, incoming);

    await expect(page.getByText(FPCALC_WARNING)).toBeVisible();
  });
});
