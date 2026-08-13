import { afterEach, describe, expect, it, vi } from "vitest";
import { createCollection, rescanCollection } from "./api";
import type { ScanProgress } from "./types";

/**
 * These drive the real fetch path with a stubbed server, because
 * readScanStream is module-private and exporting it purely for a test would
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

const progress = (scanned: number, currentPath: string | null) => ({
  scanned,
  added: scanned,
  updated: 0,
  deleted: 0,
  skipped_non_audio: 0,
  matched: 0,
  current_path: currentPath,
});

const finished = {
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

const PATH_ONE = `D:${B}Music${B}Sigur Rós${B}Hoppípolla.flac`;
const PATH_TWO = `D:${B}Music${B}Björk${B}Jóga.flac`;

const wholeBody =
  frame("progress", progress(1, PATH_ONE)) +
  frame("progress", progress(2, PATH_TWO)) +
  frame("done", finished);

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

function serverSends(
  body: BodyInit | null,
  init: ResponseInit = {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  },
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
    streamServer(wholeBody);
    const seen: ScanProgress[] = [];

    const result = await rescanCollection(1, (p) => seen.push(p));

    expect(result).toEqual(finished);
    expect(seen).toEqual([progress(1, PATH_ONE), progress(2, PATH_TWO)]);
  });

  // The chunk size is the whole point of this one. At one byte per read, every
  // frame boundary and every multi-byte character is split across two chunks,
  // so it fails without the buffer and without decode({ stream: true }).
  it.each([1, 3, 17, 10_000])(
    "gives the same answer at %i bytes per chunk",
    async (chunkSize) => {
      streamServer(wholeBody, chunkSize);
      const seen: ScanProgress[] = [];

      const result = await rescanCollection(1, (p) => seen.push(p));

      expect(result).toEqual(finished);
      expect(seen.map((p) => p.current_path)).toEqual([PATH_ONE, PATH_TWO]);
    },
  );

  it("keeps backslashes and non-ASCII characters byte-exact", async () => {
    streamServer(wholeBody, 1);
    const seen: ScanProgress[] = [];

    const result = await rescanCollection(1, (p) => seen.push(p));

    expect(seen[0].current_path).toBe(PATH_ONE);
    expect([...PATH_ONE].filter((c) => c === B)).toHaveLength(3);
    expect(result.collection.root_path).toBe(`D:${B}Music`);
  });

  it("works without a progress callback", async () => {
    streamServer(wholeBody);
    await expect(rescanCollection(1)).resolves.toEqual(finished);
  });

  // Forward compatibility: the backend may add a frame, most likely "start".
  // An older frontend has to ignore what it does not recognize.
  it("ignores an unknown event name", async () => {
    streamServer(frame("start", { id: 7 }) + wholeBody, 7);
    await expect(rescanCollection(1)).resolves.toEqual(finished);
  });

  it("uses the same reader for createCollection", async () => {
    streamServer(wholeBody);
    await expect(createCollection("Theirs", `D:${B}Music`)).resolves.toEqual(
      finished,
    );
  });
});

describe("failures", () => {
  it("throws the detail of an error frame", async () => {
    streamServer(
      frame("progress", progress(1, PATH_ONE)) +
        frame("error", { detail: "the drive went away" }),
      5,
    );
    await expect(rescanCollection(1)).rejects.toThrow("the drive went away");
  });

  // Without this the promise resolves undefined, CollectionsView stores a null
  // result, and a dead backend reads as a scan that quietly did nothing.
  it("throws when the stream ends with no done frame", async () => {
    streamServer(frame("progress", progress(1, PATH_ONE)));
    await expect(rescanCollection(1)).rejects.toThrow("ended without a result");
  });

  it("throws when the done frame is cut off mid-frame", async () => {
    streamServer(wholeBody.slice(0, wholeBody.length - 30), 5);
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
