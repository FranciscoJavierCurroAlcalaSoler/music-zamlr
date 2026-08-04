import type {
  Diff,
  ImportPreview,
  ImportResult,
  ImportRequestBody,
  Collection,
  ScanResult,
} from "./types";

export const API_BASE = "http://localhost:8000";

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

const VALUE_ERROR_PREFIX = "Value error, ";

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

export async function fetchCollections(): Promise<Collection[]> {
  const response = await fetch(`${API_BASE}/api/collections`);
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}

export async function createCollection(
  name: string,
  rootPath: string,
): Promise<ScanResult> {
  const response = await fetch(`${API_BASE}/api/collections/scan`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name, root_path: rootPath }),
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}

export async function rescanCollection(
  collectionId: number,
): Promise<ScanResult> {
  const response = await fetch(
    `${API_BASE}/api/collections/${collectionId}/rescan`,
    {
      method: "POST",
    },
  );
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}

/** Turn whatever a failed fetch produced into something worth showing. */
export function describeFetchError(error: unknown): string {
  // fetch() rejects with a TypeError only when the request never completed
  // at all: the backend is not running, the port is wrong, or CORS refused
  // it. That is by far the most common failure while developing, and the
  // raw "Failed to fetch" tells the user nothing about what to do.
  if (error instanceof TypeError) {
    return `Could not reach the server at ${API_BASE}. Is the backend running?`;
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
): Promise<Diff> {
  const response = await fetch(
    `${API_BASE}/api/diff?mine=${mineId}&theirs=${theirsId}`,
  );
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}

export async function previewImport(
  request: ImportRequestBody,
): Promise<ImportPreview> {
  const response = await fetch(`${API_BASE}/api/import/preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}

export async function executeImport(
  request: ImportRequestBody,
): Promise<ImportResult> {
  const response = await fetch(`${API_BASE}/api/import/execute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    await throwForResponse(response);
  }
  return response.json();
}
