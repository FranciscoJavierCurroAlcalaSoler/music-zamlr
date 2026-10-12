import { existsSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./fixtures";
import { MAIN_FILES, addCollection, musicFolder, uniqueName } from "./library";

test("adds a collection and lists it with its scan", async ({
  page,
}, testInfo) => {
  const name = uniqueName(testInfo, "Added");
  const folder = musicFolder(testInfo, "music", MAIN_FILES);
  // One file that is not audio: the scan counts it as seen, not as a track.
  writeFileSync(join(folder, "notes.txt"), "not a track");
  await page.goto("/");

  await page.getByLabel("Collection name").fill(name);
  await page.getByLabel("Folder path").fill(folder);
  await page.getByRole("button", { name: "Create collection" }).click();

  await expect(
    page.getByRole("heading", { name: `Scan finished — ${name}` }),
  ).toBeVisible();
  await expect(page.getByText("No problems.")).toBeVisible();
  for (const chip of ["Scanned: 4", "Added: 3", "Not audio: 1"]) {
    await expect(page.getByText(chip, { exact: true })).toBeVisible();
  }
  const row = page.getByRole("row").filter({ hasText: name });
  await expect(row.getByRole("cell").nth(1)).toHaveText(folder);
  // The scan time as the table formats it, never the raw ISO value or
  // "Invalid Date".
  await expect(row.getByRole("cell").nth(2)).toHaveText(
    /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/,
  );
  // The form empties only once the new row is in the list.
  await expect(page.getByLabel("Collection name")).toHaveValue("");
});

test.describe("a folder that does not exist", () => {
  // The browser reports the refused request itself.
  test.use({ allowedConsoleErrors: [/Failed to load resource/] });

  test("is refused, and no collection is added", async ({ page }, testInfo) => {
    const name = uniqueName(testInfo, "Missing");
    await page.goto("/");

    await page.getByLabel("Collection name").fill(name);
    await page
      .getByLabel("Folder path")
      .fill(testInfo.outputPath("no-such-folder"));
    await page.getByRole("button", { name: "Create collection" }).click();

    await expect(page.getByRole("alert")).toContainText(
      "Collection path does not exist or is not a directory.",
    );
    await expect(page.getByRole("row").filter({ hasText: name })).toHaveCount(
      0,
    );
  });
});

test("removing a collection keeps its files", async ({
  page,
  request,
}, testInfo) => {
  const name = uniqueName(testInfo, "Removed");
  const kept = uniqueName(testInfo, "Kept");
  const folder = musicFolder(testInfo, "music", MAIN_FILES);
  await addCollection(request, name, folder);
  await addCollection(request, kept, musicFolder(testInfo, "kept", MAIN_FILES));
  await page.goto("/");
  const row = page.getByRole("row").filter({ hasText: name });
  const dialog = page.getByRole("dialog");

  await row.getByRole("button", { name: "Remove" }).click();
  await expect(dialog).toContainText(`Remove "${name}" from Music Zamlr?`);
  await expect(dialog).toContainText(
    `The files in ${folder} stay where they are.`,
  );
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(row).toHaveCount(1);

  await row.getByRole("button", { name: "Remove" }).click();
  await dialog.getByRole("button", { name: "Remove" }).click();
  await expect(row).toHaveCount(0);
  for (const file of MAIN_FILES) {
    expect(existsSync(join(folder, file)), file).toBe(true);
  }

  // The Compare tab no longer offers it.
  await page.getByRole("tab", { name: "Compare" }).click();
  await page.getByRole("combobox", { name: "Main collection" }).click();
  // The kept collection proves the list is open: with the menu shut, every
  // option would be absent and the check below would prove nothing.
  await expect(
    page.getByRole("option", { name: kept, exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("option", { name, exact: true })).toHaveCount(0);
  await page.keyboard.press("Escape");
});
