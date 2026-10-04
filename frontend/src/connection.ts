declare global {
  var __ZAMLR__:
    { apiBase?: string; token?: string; logPath?: string } | undefined;
  // Tauri puts this in every webview it creates, before any script of the
  // page runs. Nothing else in this project uses it; isDesktop does, for the
  // reason written there.
  var __TAURI_INTERNALS__: object | undefined;
}

export const TOKEN_HEADER = "X-Zamlr-Token";

/**
 * Thrown inside the shell before the backend has announced its port.
 *
 * Its own type because the retry has to tell it apart from an answer: the
 * splash waits through it, and gives up at once on anything a server said.
 */
export class BackendNotAnnouncedError extends Error {}

/**
 * Say whether this page is running inside the desktop shell.
 *
 * Tauri's own global, not ours, and that is the whole point. __ZAMLR__
 * arrives when the backend has announced its port, which is a second or two
 * after the page loads — too late for anything read while a component
 * renders. A component asking our global renders its answer once, as false,
 * and nothing re-renders it when the injection lands: the browse buttons
 * never appeared in the window for exactly that reason.
 */
export function isDesktop(): boolean {
  return globalThis.__TAURI_INTERNALS__ !== undefined;
}

/**
 * Where the backend is.
 *
 * Inside the shell there is one right answer and no second guess. The
 * fallbacks below exist for a browser during development, and letting them
 * apply in the app would be worse than failing: with anything at all
 * listening on 8000 — a development backend, another copy of this tool —
 * the window would quietly talk to it instead of to the backend it started,
 * showing someone else's collections over its own empty database, with
 * nothing on screen to say so.
 *
 * Throwing is right because the splash already handles it: waitForBackend
 * retries, and a failure there is the loud one with the address and the log
 * path in it.
 */
export function apiBase(): string {
  const injected = globalThis.__ZAMLR__?.apiBase;
  if (injected !== undefined) {
    return injected;
  }
  if (isDesktop()) {
    throw new BackendNotAnnouncedError(
      "The backend has not announced its address yet.",
    );
  }
  return import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
}

export function authHeaders(): Record<string, string> {
  const token = globalThis.__ZAMLR__?.token;
  return token ? { [TOKEN_HEADER]: token } : {};
}

export function logPath(): string | null {
  return globalThis.__ZAMLR__?.logPath ?? null;
}

/**
 * The address to put in a sentence a person reads.
 *
 * apiBase throws inside the shell until the backend announces itself, and a
 * message about a failure must never fail while it is being written. Here
 * that state has a name instead.
 */
export function addressForMessage(): string {
  try {
    return apiBase();
  } catch {
    return "the backend this app starts";
  }
}
