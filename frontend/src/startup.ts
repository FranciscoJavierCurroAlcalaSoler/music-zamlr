import { fetchHealth } from "./api";
import {
  BackendNotAnnouncedError,
  addressForMessage,
  logPath,
} from "./connection";

/**
 * Waiting for the backend to come up, kept out of the component.
 *
 * The shell opens its window before the backend exists, so the page has to
 * wait. It also has to stop waiting: a backend that failed to start is the
 * likeliest fault in a packaged app, and a spinner that never ends is the
 * worst way to report it.
 *
 * Vitest runs with no DOM, so logic inside a component has no test at all.
 * That is why this lives here, as format.ts and comparison.ts do.
 */

// About fifteen seconds in all. A cold interpreter needs two seconds to
// import FastAPI and the app, and a packaged binary more, so the budget has
// to leave room for a slow first start on a slow machine.
export const ATTEMPTS = 30;
export const DELAY_MS = 500;
// Shorter than the budget, and longer than any answer a running server
// takes. One attempt that hangs must not consume the whole of it.
export const ATTEMPT_TIMEOUT_MS = 2000;

export function startupFailureMessage(
  address: string,
  logFile: string | null,
): string {
  const seconds = Math.round((ATTEMPTS * DELAY_MS) / 1000);
  return (
    `The backend did not answer at ${address} within ${seconds} seconds. ` +
    // The space that joins the sentences belongs to the optional one, not to
    // this one. Put it here and the message ends in a space whenever no log
    // file is known, which is every run outside the packaged app.
    `Close the app and open it again.` +
    (logFile === null ? "" : ` The log file at ${logFile} holds the reason.`)
  );
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

/**
 * Say whether an error means "nothing answered yet".
 *
 * Two shapes mean it. fetch rejects with a TypeError when the request never
 * completed at all, which is the backend not being up. And an attempt that
 * runs past ATTEMPT_TIMEOUT_MS is aborted by its signal, which rejects with
 * a TimeoutError rather than a TypeError — a server that is listening but
 * not yet accepting produces exactly that.
 *
 * Anything else came from a server that answered. A 401 from a wrong token
 * never becomes a 200 by being asked again, and retrying one would spend
 * the whole budget and then report the wrong cause.
 */
function meansNothingAnswered(error: unknown): boolean {
  if (error instanceof TypeError) {
    return true;
  }
  // The shell has not injected the address yet, which is the same situation
  // as a backend that has not opened its port: wait and ask again.
  if (error instanceof BackendNotAnnouncedError) {
    return true;
  }
  return error instanceof Error && error.name === "TimeoutError";
}

interface WaitOptions {
  check?: (signal?: AbortSignal) => Promise<void>;
  wait?: (milliseconds: number) => Promise<void>;
  attempts?: number;
  delayMs?: number;
}

/**
 * Ask the backend until it answers, and give up at the end of the budget.
 *
 * check and wait arrive as parameters so that a test can pass a counter and
 * a wait that returns at once. The whole retry then runs in no time, and no
 * fake clock has to be installed and taken away again.
 */
export async function waitForBackend({
  check = fetchHealth,
  wait = sleep,
  attempts = ATTEMPTS,
  delayMs = DELAY_MS,
}: WaitOptions = {}): Promise<void> {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await check(AbortSignal.timeout(ATTEMPT_TIMEOUT_MS));
      return;
    } catch (error: unknown) {
      if (!meansNothingAnswered(error)) {
        throw error;
      }
      if (attempt === attempts) {
        // cause carries the last failure, which is what the lint rule
        // asks for and what a reader in the console needs: the sentence
        // here says what to do, the cause says what actually happened.
        throw new Error(startupFailureMessage(addressForMessage(), logPath()), {
          cause: error,
        });
      }
      await wait(delayMs);
    }
  }
}
