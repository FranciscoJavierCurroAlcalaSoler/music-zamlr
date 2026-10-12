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

/** The header every request to the backend needs. */
export const AUTH = { "X-Zamlr-Token": TOKEN };

export type Frame = { event: string; data: unknown };

/**
 * The frames of a server-sent event stream, read whole. Each frame is an
 * "event:" line and a "data:" line holding JSON, and a blank line ends it.
 */
export function frames(body: string): Frame[] {
  return body
    .split("\n\n")
    .filter((block) => block.trim() !== "")
    .map((block) => {
      const lines = block.trim().split("\n");
      const event = lines.find((line) => line.startsWith("event: "));
      const data = lines.find((line) => line.startsWith("data: "));
      return {
        event: event?.slice("event: ".length) ?? "",
        data: JSON.parse(data?.slice("data: ".length) ?? "null"),
      };
    });
}

/** The data of the stream's done frame. A stream without one fails the test. */
export function doneData(all: Frame[]): Record<string, unknown> {
  const done = all.find((frame) => frame.event === "done");
  expect(done, `no done frame in ${JSON.stringify(all)}`).toBeDefined();
  return done!.data as Record<string, unknown>;
}

/** Scan a folder into a new collection through the API; return the frames. */
export async function scanFrames(
  request: APIRequestContext,
  name: string,
  rootPath: string,
  backendUrl: string = BACKEND_URL,
): Promise<Frame[]> {
  const response = await request.post(`${backendUrl}/api/collections/scan`, {
    headers: AUTH,
    data: { name, root_path: rootPath },
  });
  expect(response.ok(), await response.text()).toBe(true);
  return frames(await response.text());
}

/** Scan a folder into a new collection through the API; return its id. */
export async function addCollection(
  request: APIRequestContext,
  name: string,
  rootPath: string,
  backendUrl: string = BACKEND_URL,
): Promise<number> {
  const result = doneData(
    await scanFrames(request, name, rootPath, backendUrl),
  );
  return (result.collection as { id: number }).id;
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
