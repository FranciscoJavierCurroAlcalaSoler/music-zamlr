import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createCollection,
  fetchCollections,
  fetchDiff,
  fetchFormatOrder,
  rescanCollection,
  previewImport,
  executeImport,
  saveFormatOrder,
} from "./api";
import type {
  ScanProgress,
  DiffProgress,
  ImportProgress,
  ImportRequestBody,
} from "./types";

/**
 * These drive the real fetch path with a stubbed server, because
 * readStream is module-private and exporting it purely for a test would
 * widen the API for the test's convenience. Going through rescanCollection
 * also covers the guards that sit around it.
 */

const encoder = new TextEncoder();

// A real backslash, built rather than typed: "\M" is not an escape sequence,
// so TypeScript silently drops the backslash and the assertion then passes
// against a path that never had one.
const B = String.fromCharCode(92);

function frame(event: string, payload: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

const progressScan = (scanned: number, currentPath: string | null) => ({
  scanned,
  added: scanned,
  updated: 0,
  deleted: 0,
  skipped_non_audio: 0,
  matched: 0,
  current_path: currentPath,
});

const finishedScan = {
  scanned: 3,
  added: 3,
  updated: 0,
  deleted: 0,
  skipped_non_audio: 0,
  matched: 0,
  unreadable_files: [],
  unreadable_directories: [],
  collection: {
    id: 7,
    name: "Theirs",
    root_path: `D:${B}Music`,
    last_scanned_at: "2026-08-13T20:31:00",
  },
};

const progressDiff = (processed: number, currentPath: string | null) => ({
  theirs_processed_count: processed,
  theirs_count: 3,
  hashed_count: 1,
  current_path: currentPath,
});

const finishedDiff = {
  match_results: {
    missing: [],
    upgrade_available: [],
    already_have: [],
    needs_review: [],
    only_in_mine: [],
  },
  match_counts: {
    missing: 0,
    upgrade_available: 0,
    already_have: 0,
    needs_review: 0,
    only_in_mine: 0,
  },
};

// The union, not string. A fixture typed string can build a phase the backend
// cannot send, and the assertion then compares that typo against itself and
// passes. It is also the second place a third phase breaks the build, after
// describePhase's satisfies.
const progressImport = (
  phase: ImportProgress["phase"],
  processedCount: number,
  totalCount: number,
  currentPath: string | null,
) => ({
  phase,
  processed_count: processedCount,
  total_count: totalCount,
  current_path: currentPath,
});

const finishedPreview = {
  operations: [
    {
      source: "track.mp3",
      destination: "track.mp3",
      action: "copy",
      group_id: 1,
      overwrites: false,
    },
  ],
  upgrades: [],
  operation_counts: { copy: 1, delete: 0, move: 0, overwrites: 0 },
};

const finishedImport = {
  operations: [
    {
      operation: {
        source: "track.mp3",
        destination: "track.mp3",
        action: "copy",
        group_id: 1,
        overwrites: false,
      },
      status: "success",
      error: null,
    },
  ],
  status_counts: { success: 1, failed: 0, skipped: 0 },
  log_path: null,
  log_error: null,
};

/**
 * Both import endpoints take a body, and the stubbed fetch ignores it: it
 * takes no parameters at all. So these values are never read by anything,
 * and one shared fixture is right — a per-test body would imply the request
 * changes the answer, which it cannot here.
 *
 * Annotated rather than inferred. A const literal widens "mirror" to string,
 * and string is not a StructureMode.
 */
const importRequest: ImportRequestBody = {
  track_ids: [1, 2],
  mine_collection_id: 1,
  theirs_collection_id: 2,
  destination_root: `D:${B}Music`,
  structure_mode: "mirror",
  upgrade_action: "keep_both",
  resolutions: [],
};

const PATH_ONE = `D:${B}Music${B}Sigur Rós${B}Hoppípolla.flac`;
const PATH_TWO = `D:${B}Music${B}Björk${B}Jóga.flac`;

const wholeBodyScan =
  frame("progress", progressScan(1, PATH_ONE)) +
  frame("progress", progressScan(2, PATH_TWO)) +
  frame("done", finishedScan);

const wholeBodyDiff =
  frame("progress", progressDiff(1, PATH_ONE)) +
  frame("progress", progressDiff(2, PATH_TWO)) +
  frame("done", finishedDiff);

const wholeBodyPreview =
  frame("progress", progressImport("comparing", 111, 3500, PATH_ONE)) +
  frame("progress", progressImport("comparing", 666, 3500, PATH_TWO)) +
  frame("done", finishedPreview);

const wholeBodyImport =
  frame("progress", progressImport("comparing", 111, 3500, PATH_ONE)) +
  frame("progress", progressImport("comparing", 666, 3500, PATH_TWO)) +
  frame("progress", progressImport("copying", 11, 42, PATH_ONE)) +
  frame("progress", progressImport("copying", 33, 42, PATH_TWO)) +
  frame("done", finishedImport);

/**
 * Hand the body over in fixed-size byte chunks. A chunk size of 1 puts a
 * boundary inside every frame separator and inside every multi-byte
 * character, which is the pair of failures a hand-written reader gets wrong.
 */
function streamOf(text: string, chunkSize: number): ReadableStream<Uint8Array> {
  const bytes = encoder.encode(text);
  let offset = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (offset >= bytes.length) {
        controller.close();
        return;
      }
      controller.enqueue(bytes.slice(offset, offset + chunkSize));
      offset += chunkSize;
    },
  });
}

const STREAM_RESPONSE: ResponseInit = {
  status: 200,
  headers: { "content-type": "text/event-stream" },
};

function serverSends(
  body: BodyInit | null,
  init: ResponseInit = STREAM_RESPONSE,
) {
  vi.stubGlobal("fetch", () => Promise.resolve(new Response(body, init)));
}

function streamServer(text: string, chunkSize = 10_000) {
  serverSends(streamOf(text, chunkSize));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("reading a scan stream", () => {
  it("resolves with the done frame and reports every progress frame", async () => {
    streamServer(wholeBodyScan);
    const seen: ScanProgress[] = [];

    const result = await rescanCollection(1, (p) => seen.push(p));

    expect(result).toEqual(finishedScan);
    expect(seen).toEqual([
      progressScan(1, PATH_ONE),
      progressScan(2, PATH_TWO),
    ]);
  });

  // The chunk size is the whole point of this one. At one byte per read, every
  // frame boundary and every multi-byte character is split across two chunks,
  // so it fails without the buffer and without decode({ stream: true }).
  it.each([1, 3, 17, 10_000])(
    "gives the same answer at %i bytes per chunk",
    async (chunkSize) => {
      streamServer(wholeBodyScan, chunkSize);
      const seen: ScanProgress[] = [];

      const result = await rescanCollection(1, (p) => seen.push(p));

      expect(result).toEqual(finishedScan);
      expect(seen.map((p) => p.current_path)).toEqual([PATH_ONE, PATH_TWO]);
    },
  );

  it("keeps backslashes and non-ASCII characters byte-exact", async () => {
    streamServer(wholeBodyScan, 1);
    const seen: ScanProgress[] = [];

    const result = await rescanCollection(1, (p) => seen.push(p));

    expect(seen[0].current_path).toBe(PATH_ONE);
    expect([...PATH_ONE].filter((c) => c === B)).toHaveLength(3);
    expect(result.collection.root_path).toBe(`D:${B}Music`);
  });

  it("works without a progress callback", async () => {
    streamServer(wholeBodyScan);
    await expect(rescanCollection(1)).resolves.toEqual(finishedScan);
  });

  // Forward compatibility: the backend may add a frame, most likely "start".
  // An older frontend has to ignore what it does not recognize.
  it("ignores an unknown event name", async () => {
    streamServer(frame("start", { id: 7 }) + wholeBodyScan, 7);
    await expect(rescanCollection(1)).resolves.toEqual(finishedScan);
  });

  it("uses the same reader for createCollection", async () => {
    streamServer(wholeBodyScan);
    await expect(createCollection("Theirs", `D:${B}Music`)).resolves.toEqual(
      finishedScan,
    );
  });
});

/**
 * These exercise the shared reader, not the scan. Every endpoint goes through
 * one readStream, so each case below behaves identically through fetchDiff and
 * needs no per-endpoint copy — running the same code twice would double the
 * maintenance and prove nothing new. rescanCollection is simply the cheapest
 * way in.
 *
 * The exception is the label, which is the one failure that differs by caller.
 * That one lives with its endpoint, in "reading a diff stream".
 */
describe("failures", () => {
  it("throws the detail of an error frame", async () => {
    streamServer(
      frame("progress", progressScan(1, PATH_ONE)) +
        frame("error", { detail: "the drive went away" }),
      5,
    );
    await expect(rescanCollection(1)).rejects.toThrow("the drive went away");
  });

  // Without this the promise resolves undefined, CollectionsView stores a null
  // result, and a dead backend reads as a scan that quietly did nothing.
  it("throws when the stream ends with no done frame", async () => {
    streamServer(frame("progress", progressScan(1, PATH_ONE)));
    await expect(rescanCollection(1)).rejects.toThrow("scan");
  });

  it("throws when the done frame is cut off mid-frame", async () => {
    streamServer(wholeBodyScan.slice(0, wholeBodyScan.length - 30), 5);
    await expect(rescanCollection(1)).rejects.toThrow("ended without a result");
  });

  // The exact shape of a backend still running pre-Phase-4 code: a valid JSON
  // body that parses cleanly and is not a stream.
  it("names the cause when the response is not an event stream", async () => {
    serverSends(JSON.stringify({ scanned: 12, added: 0 }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
    await expect(rescanCollection(1)).rejects.toThrow(
      "Expected an event stream",
    );
  });

  // A request rejected before the stream opens is ordinary JSON, and must keep
  // going through throwForResponse so the backend's own detail reaches the UI.
  it("prefers the backend's detail when the request never opens a stream", async () => {
    serverSends(JSON.stringify({ detail: "Collection path not found." }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
    await expect(rescanCollection(1)).rejects.toThrow(
      "Collection path not found.",
    );
  });
});

describe("reading a diff stream", () => {
  it("resolves with the diff and reports every progress frame", async () => {
    streamServer(wholeBodyDiff);
    const seen: DiffProgress[] = [];

    const result = await fetchDiff(1, 2, (p) => seen.push(p));

    expect(result).toEqual(finishedDiff);
    expect(seen).toEqual([
      progressDiff(1, PATH_ONE),
      progressDiff(2, PATH_TWO),
    ]);
  });

  it.each([1, 3, 17, 10_000])(
    "gives the same answer at %i bytes per chunk",
    async (chunkSize) => {
      streamServer(wholeBodyDiff, chunkSize);
      const seen: DiffProgress[] = [];

      const result = await fetchDiff(1, 2, (p) => seen.push(p));

      expect(result).toEqual(finishedDiff);
      expect(seen.map((p) => p.current_path)).toEqual([PATH_ONE, PATH_TWO]);
    },
  );

  it("says comparison, not scan, when the stream ends without a result", async () => {
    streamServer(frame("progress", progressDiff(1, PATH_ONE)));

    await expect(fetchDiff(1, 2)).rejects.toThrow("comparison");
  });
});

describe("reading an import stream", () => {
  it("resolves with the preview and reports every progress frame", async () => {
    streamServer(wholeBodyPreview);
    const seen: ImportProgress[] = [];

    const result = await previewImport(importRequest, (p) => seen.push(p));

    expect(result).toEqual(finishedPreview);
    expect(seen).toEqual([
      progressImport("comparing", 111, 3500, PATH_ONE),
      progressImport("comparing", 666, 3500, PATH_TWO),
    ]);
  });

  it("resolves with the result and reports both phases in order", async () => {
    streamServer(wholeBodyImport);
    const seen: ImportProgress[] = [];

    const result = await executeImport(importRequest, (p) => seen.push(p));

    expect(result).toEqual(finishedImport);
    expect(seen.map((p) => p.phase)).toEqual([
      "comparing",
      "comparing",
      "copying",
      "copying",
    ]);
  });

  it("carries a different total in each phase", async () => {
    streamServer(wholeBodyImport);
    const seen: ImportProgress[] = [];

    const result = await executeImport(importRequest, (p) => seen.push(p));

    expect(result).toEqual(finishedImport);
    expect(seen.map((p) => p.total_count)).toEqual([3500, 3500, 42, 42]);
  });

  it.each([1, 3, 17, 10_000])(
    "gives the same answer at %i bytes per chunk",
    async (chunkSize) => {
      streamServer(wholeBodyImport, chunkSize);
      const seen: ImportProgress[] = [];

      const result = await executeImport(importRequest, (p) => seen.push(p));

      expect(result).toEqual(finishedImport);
      expect(seen.map((p) => p.current_path)).toEqual([
        PATH_ONE,
        PATH_TWO,
        PATH_ONE,
        PATH_TWO,
      ]);
    },
  );

  it("says preview, not scan or comparison, when the stream ends without a result", async () => {
    streamServer(
      frame("progress", progressImport("comparing", 111, 3500, PATH_ONE)),
    );

    await expect(previewImport(importRequest)).rejects.toThrow("preview");
  });

  it("says import, not scan, comparison or preview, when the stream ends without a result", async () => {
    streamServer(
      frame("progress", progressImport("comparing", 111, 3500, PATH_ONE)),
    );

    await expect(executeImport(importRequest)).rejects.toThrow("import");
  });
});

describe("the format order", () => {
  const savedOrder = {
    tiers: [["FLAC"], ["MP3"]],
    default_tiers: [["FLAC"], ["MP3"]],
    placed: [],
    lossy_formats: ["MP3"],
    updated_at: "2026-09-17T16:02:00",
  };

  function jsonServer(body: unknown, status = 200) {
    const calls: RequestInit[] = [];
    vi.stubGlobal("fetch", (_url: string, init: RequestInit = {}) => {
      calls.push(init);
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "content-type": "application/json" },
        }),
      );
    });
    return calls;
  }

  it("reads the saved order", async () => {
    jsonServer(savedOrder);

    await expect(fetchFormatOrder()).resolves.toEqual(savedOrder);
  });

  it("saves an order with PUT, which is the method the endpoint answers", async () => {
    const calls = jsonServer(savedOrder);

    await saveFormatOrder([["FLAC"], ["MP3"]]);

    expect(calls[0].method).toBe("PUT");
    expect(JSON.parse(String(calls[0].body))).toEqual({
      tiers: [["FLAC"], ["MP3"]],
    });
  });

  it("throws the message the server sends when an order is refused", async () => {
    // The detail names the format at fault, and the editor shows it: without
    // this path the user is told only that something went wrong.
    jsonServer({ detail: "mixed lossy and non-lossy formats: FLAC, MP3" }, 400);

    await expect(saveFormatOrder([["FLAC", "MP3"]])).rejects.toThrow(
      "mixed lossy and non-lossy formats: FLAC, MP3",
    );
  });
});

/**
 * Every request function, because each one builds its own headers and a
 * spread goes missing in one place at a time. With a single function under
 * test, the token could vanish from the other seven and nothing would say
 * so — which is what the mutations showed before this table existed.
 */
describe("the token header", () => {
  const JSON_RESPONSE = {
    status: 200,
    headers: { "content-type": "application/json" },
  };

  function recordingServer(body: string, init: ResponseInit = STREAM_RESPONSE) {
    const calls: RequestInit[] = [];
    vi.stubGlobal("fetch", (_url: string, requestInit: RequestInit = {}) => {
      calls.push(requestInit);
      // Built inside the stub, so each call gets a body of its own rather
      // than a stream another call has already drained.
      return Promise.resolve(new Response(body, init));
    });
    return calls;
  }

  const cases: [string, () => RequestInit[], () => Promise<unknown>][] = [
    [
      "fetchCollections",
      () => recordingServer("[]", JSON_RESPONSE),
      () => fetchCollections(),
    ],
    [
      "fetchFormatOrder",
      () => recordingServer("{}", JSON_RESPONSE),
      () => fetchFormatOrder(),
    ],
    [
      "saveFormatOrder",
      () => recordingServer("{}", JSON_RESPONSE),
      () => saveFormatOrder([["FLAC"], ["MP3"]]),
    ],
    [
      "createCollection",
      () => recordingServer(wholeBodyScan),
      () => createCollection("Theirs", `D:${B}Music`),
    ],
    [
      "rescanCollection",
      () => recordingServer(wholeBodyScan),
      () => rescanCollection(1),
    ],
    ["fetchDiff", () => recordingServer(wholeBodyDiff), () => fetchDiff(1, 2)],
    [
      "previewImport",
      () => recordingServer(wholeBodyPreview),
      () => previewImport(importRequest),
    ],
    [
      "executeImport",
      () => recordingServer(wholeBodyImport),
      () => executeImport(importRequest),
    ],
  ];

  it.each(cases)("%s sends the injected token", async (_name, server, call) => {
    vi.stubGlobal("__ZAMLR__", { token: "test-token" });
    const calls = server();

    await call();

    // The value, not expect.any(String): a header hard-coded to anything at
    // all would satisfy a looser assertion.
    expect(calls[0].headers).toEqual(
      expect.objectContaining({ "X-Zamlr-Token": "test-token" }),
    );
  });

  it("sends no token header when nothing is injected", async () => {
    const calls = recordingServer("[]", JSON_RESPONSE);

    await fetchCollections();

    expect(calls[0].headers).not.toHaveProperty("X-Zamlr-Token");
  });
});
