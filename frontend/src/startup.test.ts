import { afterEach, describe, expect, it } from "vitest";

import { BackendNotAnnouncedError } from "./connection";
import { ATTEMPTS, startupFailureMessage, waitForBackend } from "./startup";

afterEach(() => {
  delete globalThis.__ZAMLR__;
});

// Returns at once, so a test of thirty attempts costs nothing. This is what
// the wait parameter is for: no fake clock to install and take away again.
const noWait = () => Promise.resolve();

function unreachable(): Promise<void> {
  // The error fetch itself produces when the request never completed. The
  // retry turns on this type, so a plain Error here would test nothing.
  return Promise.reject(new TypeError("Failed to fetch"));
}

describe("waitForBackend", () => {
  it("returns as soon as the backend answers", async () => {
    let calls = 0;
    const check = () => {
      calls += 1;
      return Promise.resolve();
    };

    await waitForBackend({ check, wait: noWait });

    expect(calls).toBe(1);
  });

  it("retries while the backend is unreachable", async () => {
    let calls = 0;
    const check = () => {
      calls += 1;
      return calls < 3 ? unreachable() : Promise.resolve();
    };

    await waitForBackend({ check, wait: noWait });

    // The count, not only the resolution. A function that never retried
    // would also resolve here if the first call happened to succeed.
    expect(calls).toBe(3);
  });

  it("gives up after the last attempt", async () => {
    let calls = 0;
    const check = () => {
      calls += 1;
      return unreachable();
    };

    await expect(
      waitForBackend({ check, wait: noWait, attempts: 4 }),
    ).rejects.toThrow("did not answer");

    // Four, exactly. A rejection on its own passes against a function that
    // gives up after one attempt, which is the opposite of this feature.
    expect(calls).toBe(4);
  });

  it("retries an attempt that timed out", async () => {
    // What AbortSignal.timeout produces: a server that listens but has not
    // begun to accept, which is the normal case for the first second.
    const timedOut = () => {
      const error = new Error("The operation timed out.");
      error.name = "TimeoutError";
      return Promise.reject(error);
    };
    let calls = 0;
    const check = () => {
      calls += 1;
      return calls < 2 ? timedOut() : Promise.resolve();
    };

    await waitForBackend({ check, wait: noWait });

    expect(calls).toBe(2);
  });

  it("waits while the shell has not announced the address yet", async () => {
    // The first polls in the desktop app happen before the backend has
    // announced its port, so apiBase throws this. Treated as an answer, the
    // splash would give up a second after the window opened.
    let calls = 0;
    const check = () => {
      calls += 1;
      return calls < 3
        ? Promise.reject(new BackendNotAnnouncedError("not yet"))
        : Promise.resolve();
    };

    await waitForBackend({ check, wait: noWait });

    expect(calls).toBe(3);
  });

  it("does not retry an answer from the server", async () => {
    let calls = 0;
    const check = () => {
      calls += 1;
      // What throwForResponse raises: the server answered, and said no.
      return Promise.reject(new Error("Invalid or missing token"));
    };

    await expect(waitForBackend({ check, wait: noWait })).rejects.toThrow(
      "Invalid or missing token",
    );

    // Once. Waiting cannot turn a wrong token into a right one, and a retry
    // would spend the whole budget and then report the wrong cause.
    expect(calls).toBe(1);
  });

  it("names the address it could not reach", async () => {
    globalThis.__ZAMLR__ = { apiBase: "http://127.0.0.1:54321" };

    await expect(
      waitForBackend({ check: unreachable, wait: noWait, attempts: 1 }),
    ).rejects.toThrow("http://127.0.0.1:54321");
  });

  it("names the log file in the message it rejects with", async () => {
    const logPath = String.raw`C:\logs\music-zamlr.log`;
    globalThis.__ZAMLR__ = {
      apiBase: "http://127.0.0.1:54321",
      logPath,
    };

    await expect(
      waitForBackend({ check: unreachable, wait: noWait, attempts: 1 }),
    ).rejects.toThrow(logPath);
  });
});

describe("startupFailureMessage", () => {
  it("names the address and the time it waited", () => {
    const message = startupFailureMessage("http://127.0.0.1:54321", null);

    expect(message).toContain("http://127.0.0.1:54321");
    expect(message).toContain("15 seconds");
  });

  it("names the log file when one is known", () => {
    const logPath = String.raw`C:\logs\music-zamlr.log`;
    const message = startupFailureMessage("http://127.0.0.1:54321", logPath);

    expect(message).toContain(logPath);
    // The join itself. Every other assertion here reads a substring that
    // sits inside one sentence, so none of them can see two sentences run
    // together, as in "again.The log file".
    expect(message).toContain("again. The log file");
  });

  it("does not end in a space when no log file is known", () => {
    const message = startupFailureMessage("http://127.0.0.1:54321", null);

    expect(message).toBe(message.trimEnd());
  });

  it("says nothing about a log file when none is known", () => {
    const message = startupFailureMessage("http://127.0.0.1:54321", null);

    expect(message).not.toContain("log");
  });

  it("is built from the budget rather than from a written number", () => {
    // The sentence above says fifteen seconds because the budget says so.
    // Without this, changing ATTEMPTS leaves a message that lies.
    expect(ATTEMPTS).toBe(30);
  });
});
