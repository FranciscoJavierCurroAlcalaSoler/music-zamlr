import { cpSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import type { APIRequestContext, Page, TestInfo } from "@playwright/test";
import { expect } from "./fixtures";
import { BACKEND_URL, TOKEN } from "./settings";

const FIXTURES = join(
  import.meta.dirname,
  "..",
  "..",
  "backend",
  "tests",
  "fixtures",
);

// Each bucket of the comparison gets one file, so each count reads 1:
//   already have   the two MP3s are byte-identical
//   upgrade        the same AAC track at 125 and at 217 kbps
//   missing        the WMA has no partner
//   only in main   the AIFF has no partner
// Every file shorter than about two seconds gives fpcalc an empty
// fingerprint, so the two incoming 1-second files that have a partner of
// their length are reported as unreadable, and the page warns about two
// files. That comes from the length, not the codec, so it holds on every
// system with the pinned fpcalc.
export const MAIN_FILES = [
  "test_track_mine.mp3",
  "test_track.aac",
  "test_track.aiff",
];
export const INCOMING_FILES = [
  "test_track_theirs.mp3",
  "test_track_aac.m4a",
  "test_track.wma",
];

/** A folder under this test's output, holding copies of the given fixtures. */
export function musicFolder(
  testInfo: TestInfo,
  name: string,
  files: string[],
): string {
  const folder = testInfo.outputPath(name);
  mkdirSync(folder, { recursive: true });
  for (const file of files) {
    cpSync(join(FIXTURES, file), join(folder, file));
  }
  return folder;
}

/**
 * A collection name no other test uses. Every test and both browsers share
 * one database for the whole run, and names must be unique in it.
 */
export function uniqueName(testInfo: TestInfo, label: string): string {
  // testId is "<file hash>-<test hash>": the file part is the same for every
  // test in one file, so only the test part tells them apart.
  const testPart = testInfo.testId.split("-").pop();
  return `${label} ${testInfo.project.name} ${testPart}`;
}

/** Scan a folder into a new collection through the API, and return its id. */
export async function addCollection(
  request: APIRequestContext,
  name: string,
  rootPath: string,
  backendUrl: string = BACKEND_URL,
): Promise<number> {
  const response = await request.post(`${backendUrl}/api/collections/scan`, {
    headers: { "X-Zamlr-Token": TOKEN },
    data: { name, root_path: rootPath },
  });
  expect(response.ok(), await response.text()).toBe(true);
  // The body is a stream of server-sent events, read whole here. The scan's
  // result is the frame named done.
  const frame = (await response.text())
    .split("\n\n")
    .find((block) => block.startsWith("event: done"));
  expect(frame, "the scan ended without a done frame").toBeDefined();
  const data = frame!.split("\n").find((line) => line.startsWith("data: "))!;
  return JSON.parse(data.slice("data: ".length)).collection.id;
}

/** Choose the two collections on the Compare tab and run the comparison. */
export async function compare(
  page: Page,
  mainName: string,
  incomingName: string,
): Promise<void> {
  await page.getByRole("tab", { name: "Compare" }).click();
  await choose(page, "Main collection", mainName);
  await choose(page, "Incoming collection", incomingName);
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(
    page.getByRole("tab", { name: /^Import candidates/ }),
  ).toBeVisible();
}

export async function choose(
  page: Page,
  picker: "Main collection" | "Incoming collection",
  name: string,
): Promise<void> {
  await page.getByRole("combobox", { name: picker }).click();
  await page.getByRole("option", { name, exact: true }).click();
}
