import type {
  DiffResult,
  DiffProgress,
  ImportPreview,
  ImportProgress,
  ImportResult,
  ImportRequestBody,
  Collection,
  ScanProgress,
  ScanResult,
  FormatOrder,
} from "./types";

import { addressForMessage, apiBase, authHeaders } from "./connection";

/**
 * Plain async functions: no hooks, no setState. Components call these and
 * update their own state from the returned promise's callbacks.
 */

/** One entry in FastAPI's 422 body: loc is the path to the offending field. */
interface ValidationErrorDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/** FastAPI error bodies carry detail as a string (raised by HTTPException) or
 *  as an array of validation errors (raised by request validation). */
interface ErrorBody {
  detail?: string | ValidationErrorDetail[];
}

interface ErrorPayload {
  detail: string;
}

const VALUE_ERROR_PREFIX = "Value error, ";
const FRAME_SEPARATOR = "\n\n";
const EVENT_PREFIX = "event: ";
const DATA_PREFIX = "data: ";

export type ScanProgressCallback = (progress: ScanProgress) => void;
export type DiffProgressCallback = (progress: DiffProgress) => void;
export type ImportProgressCallback = (progress: ImportProgress) => void;

function detailToMessage(detail: string | ValidationErrorDetail[]): string {
  if (!Array.isArray(detail)) {
    return detail;
  }
  return detail
    .map((entry) => {
      const field = entry.loc.at(-1) ?? "request";
      const message = entry.msg.startsWith(VALUE_ERROR_PREFIX)
        ? entry.msg.slice(VALUE_ERROR_PREFIX.length)
        : entry.msg;
      return `${field}: ${message}`;
    })
    .join("; ");
}

/**
 * Throw the most specific error a failed response supports.
 *
 * Prefers the backend's own `detail` over a bare status line, so a caller
 * surfaces "Collection path not found. It may not be mounted." rather than
 * "Server responded with 400". Declared as returning `never` because it
 * always throws.
 */
async function throwForResponse(response: Response): Promise<never> {
  let body: ErrorBody | null = null;
  try {
    body = await response.json();
  } catch {
    // Not every failure is JSON: an unhandled server exception or a proxy
    // can return HTML. Fall through to the status line rather than letting
    // a parse error replace the real failure.
  }
  if (body?.detail) {
    throw new Error(detailToMessage(body.detail));
  }
  throw new Error(`Server responded with ${response.status}`);
}

/**
 * Ask whether the backend is up, and say nothing about what it answered.
 *
 * The body is ignored on purpose: the question is whether this address
 * answers at all, and with the right token. A caller that wanted more would
 * be reading a contract nothing else maintains.
 *
 * `signal` is how a single attempt is bounded. The backend's socket listens
 * before uvicorn accepts, so a request made while it starts waits rather
 * than failing, and an unbounded attempt would use the whole retry budget.
 */
export async function fetchHealth(signal?: AbortSignal): Promise<void> {
  const response = await fetch(`${apiBase()}/api/health`, {
    headers: authHeaders(),
    signal,
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
}

export async function fetchCollections(): Promise<Collection[]> {
  const response = await fetch(`${apiBase()}/api/collections`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}

function parseFrame(frame: string): [string, string] {
  let eventName = "";
  let data = "";

  for (const line of frame.split("\n")) {
    if (line.startsWith(EVENT_PREFIX))
      eventName = line.slice(EVENT_PREFIX.length);
    else if (line.startsWith(DATA_PREFIX))
      data = line.slice(DATA_PREFIX.length);
  }
  return [eventName, data];
}

async function readStream<TDone, TProgress>(
  response: Response,
  label: string,
  onProgress?: (progress: TProgress) => void,
): Promise<TDone> {
  // A 200 that is not an event stream is almost always a backend running
  // older code, which answers these endpoints with a plain JSON body. Without
  // this the symptom is the generic "ended without a result" below, which
  // sends you looking at the stream reader instead of at the server.
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/event-stream")) {
    throw new Error(
      `Expected an event stream, but the server sent ${contentType || "no content type"}. ` +
        `The backend may be running older code — restart it with "fastapi dev main.py".`,
    );
  }
  if (response.body === null)
    throw new Error("The server sent no response body.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: TDone | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let index = buffer.indexOf(FRAME_SEPARATOR);
    while (index !== -1) {
      const [eventName, data] = parseFrame(buffer.slice(0, index));
      buffer = buffer.slice(index + FRAME_SEPARATOR.length);
      switch (eventName) {
        case "progress":
          onProgress?.(JSON.parse(data) as TProgress);
          break;
        case "done":
          result = JSON.parse(data) as TDone;
          break;
        case "error":
          void reader.cancel();
          throw new Error((JSON.parse(data) as ErrorPayload).detail);
        // An unknown event name is ignored rather than treated as a fault, so
        // an older frontend keeps working against a backend that adds a frame.
        default:
          break;
      }
      index = buffer.indexOf(FRAME_SEPARATOR);
    }
  }
  if (result === null)
    throw new Error(
      `The ${label} ended without a result. The server may have stopped.`,
    );
  return result;
}

export async function createCollection(
  name: string,
  rootPath: string,
  onProgress?: ScanProgressCallback,
): Promise<ScanResult> {
  const response = await fetch(`${apiBase()}/api/collections/scan`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name, root_path: rootPath }),
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
  return readStream<ScanResult, ScanProgress>(response, "scan", onProgress);
}

export async function rescanCollection(
  collectionId: number,
  onProgress?: ScanProgressCallback,
): Promise<ScanResult> {
  const response = await fetch(
    `${apiBase()}/api/collections/${collectionId}/rescan`,
    {
      method: "POST",
      headers: authHeaders(),
    },
  );
  if (!response.ok) {
    await throwForResponse(response);
  }
  return readStream<ScanResult, ScanProgress>(response, "scan", onProgress);
}

/** Turn whatever a failed fetch produced into something worth showing. */
export function describeFetchError(error: unknown): string {
  // fetch() rejects with a TypeError only when the request never completed
  // at all: the backend is not running, the port is wrong, or CORS refused
  // it. That is by far the most common failure while developing, and the
  // raw "Failed to fetch" tells the user nothing about what to do.
  if (error instanceof TypeError) {
    return `Could not reach the server at ${addressForMessage()}. Is the backend running?`;
  }
  // Anything we threw ourselves already describes a real HTTP response.
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong.";
}

export async function fetchDiff(
  mineId: number,
  theirsId: number,
  onProgress?: DiffProgressCallback,
): Promise<DiffResult> {
  const response = await fetch(
    `${apiBase()}/api/diff?mine=${mineId}&theirs=${theirsId}`,
    { headers: authHeaders() },
  );
  if (!response.ok) {
    await throwForResponse(response);
  }
  return readStream<DiffResult, DiffProgress>(
    response,
    "comparison",
    onProgress,
  );
}

export async function previewImport(
  request: ImportRequestBody,
  onProgress?: ImportProgressCallback,
): Promise<ImportPreview> {
  const response = await fetch(`${apiBase()}/api/import/preview`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
  return readStream<ImportPreview, ImportProgress>(
    response,
    "preview",
    onProgress,
  );
}

export async function executeImport(
  request: ImportRequestBody,
  onProgress?: ImportProgressCallback,
): Promise<ImportResult> {
  const response = await fetch(`${apiBase()}/api/import/execute`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
  return readStream<ImportResult, ImportProgress>(
    response,
    "import",
    onProgress,
  );
}

export async function fetchFormatOrder(): Promise<FormatOrder> {
  const response = await fetch(`${apiBase()}/api/settings/format-order`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}

export async function saveFormatOrder(tiers: string[][]): Promise<FormatOrder> {
  const response = await fetch(`${apiBase()}/api/settings/format-order`, {
    method: "PUT",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ tiers: tiers }),
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}
