import { mkdirSync } from "node:fs";
import type { APIRequestContext, TestInfo } from "@playwright/test";
import { expect, test } from "./fixtures";
import {
  AUTH,
  INCOMING_FILES,
  MAIN_FILES,
  type Frame,
  addCollection,
  doneData,
  frames,
  musicFolder,
  scanFrames,
  uniqueName,
} from "./library";
import { BACKEND_URL } from "./settings";
import {
  COLLECTION,
  DIFF_PROGRESS,
  DIFF_RESULT,
  FORMAT_ORDER,
  IMPORT_PREVIEW,
  IMPORT_PROGRESS,
  IMPORT_RESULT,
  SCAN_PROGRESS,
  SCAN_RESULT,
  problems,
} from "./shapes";

// Each check is paired with one that the checked list is not empty: an empty
// array fits every element shape, so without it a check could pass on no
// values at all.

function progressData(all: Frame[]): unknown[] {
  return all.filter((frame) => frame.event === "progress").map((f) => f.data);
}

async function compared(request: APIRequestContext, testInfo: TestInfo) {
  const mineId = await addCollection(
    request,
    uniqueName(testInfo, "Main"),
    musicFolder(testInfo, "main", MAIN_FILES),
  );
  const theirsId = await addCollection(
    request,
    uniqueName(testInfo, "Incoming"),
    musicFolder(testInfo, "incoming", INCOMING_FILES),
  );
  const response = await request.get(
    `${BACKEND_URL}/api/diff?mine=${mineId}&theirs=${theirsId}`,
    { headers: AUTH },
  );
  expect(response.ok(), await response.text()).toBe(true);
  return { mineId, theirsId, all: frames(await response.text()) };
}

test("the collections and the format order", async ({ request }, testInfo) => {
  await addCollection(
    request,
    uniqueName(testInfo, "Listed"),
    musicFolder(testInfo, "music", MAIN_FILES),
  );

  const collections = await (
    await request.get(`${BACKEND_URL}/api/collections`, { headers: AUTH })
  ).json();
  expect(collections.length).toBeGreaterThan(0);
  expect(problems(collections, { arrayOf: COLLECTION }, "collections")).toEqual(
    [],
  );

  const order = await (
    await request.get(`${BACKEND_URL}/api/settings/format-order`, {
      headers: AUTH,
    })
  ).json();
  expect(order.tiers.length).toBeGreaterThan(0);
  expect(problems(order, FORMAT_ORDER, "format order")).toEqual([]);
});

test("a scan's progress and result", async ({ request }, testInfo) => {
  const all = await scanFrames(
    request,
    uniqueName(testInfo, "Scanned"),
    musicFolder(testInfo, "music", MAIN_FILES),
  );

  const progress = progressData(all);
  expect(progress.length).toBeGreaterThan(0);
  expect(problems(progress, { arrayOf: SCAN_PROGRESS }, "progress")).toEqual(
    [],
  );
  expect(problems(doneData(all), SCAN_RESULT, "result")).toEqual([]);
});

test("a comparison's progress and result", async ({ request }, testInfo) => {
  const { all } = await compared(request, testInfo);

  const progress = progressData(all);
  expect(progress.length).toBeGreaterThan(0);
  expect(problems(progress, { arrayOf: DIFF_PROGRESS }, "progress")).toEqual(
    [],
  );
  const result = doneData(all);
  const lists = result.match_results as Record<string, unknown[]>;
  // The fixtures give one item to each of these, so each element shape is
  // checked against a real value. needs_review and rejected stay empty: no
  // fixture can fill them.
  for (const name of [
    "missing",
    "upgrade_available",
    "already_have",
    "only_in_mine",
    "unreadable_files",
  ]) {
    expect(lists[name].length, name).toBeGreaterThan(0);
  }
  expect(problems(result, DIFF_RESULT, "result")).toEqual([]);
});

test("an import's preview, progress and result", async ({
  request,
}, testInfo) => {
  const { mineId, theirsId, all } = await compared(request, testInfo);
  const lists = doneData(all).match_results as Record<
    string,
    { id?: number; theirs?: { id: number } }[]
  >;
  const destination = testInfo.outputPath("destination");
  mkdirSync(destination);
  // The missing track and the upgrade, kept beside the main file, so the
  // import copies and never deletes.
  const body = {
    track_ids: [lists.missing[0].id, lists.upgrade_available[0].theirs!.id],
    mine_collection_id: mineId,
    theirs_collection_id: theirsId,
    destination_root: destination,
    structure_mode: "flat",
    upgrade_action: "keep_both",
    resolutions: [],
  };

  const previewResponse = await request.post(
    `${BACKEND_URL}/api/import/preview`,
    { headers: AUTH, data: body },
  );
  expect(previewResponse.ok(), await previewResponse.text()).toBe(true);
  const preview = frames(await previewResponse.text());
  const previewResult = doneData(preview);
  expect((previewResult.operations as unknown[]).length).toBeGreaterThan(0);
  expect((previewResult.upgrades as unknown[]).length).toBeGreaterThan(0);
  expect(problems(previewResult, IMPORT_PREVIEW, "preview")).toEqual([]);

  const executeResponse = await request.post(
    `${BACKEND_URL}/api/import/execute`,
    { headers: AUTH, data: body },
  );
  expect(executeResponse.ok(), await executeResponse.text()).toBe(true);
  const execute = frames(await executeResponse.text());
  const progress = [...progressData(preview), ...progressData(execute)];
  // Both phases, so both values of phase are checked.
  expect(new Set(progress.map((p) => (p as { phase: string }).phase))).toEqual(
    new Set(["comparing", "copying"]),
  );
  expect(problems(progress, { arrayOf: IMPORT_PROGRESS }, "progress")).toEqual(
    [],
  );
  const result = doneData(execute);
  expect((result.operations as unknown[]).length).toBeGreaterThan(0);
  expect(problems(result, IMPORT_RESULT, "result")).toEqual([]);
});
