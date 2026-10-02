import { afterEach, describe, expect, it } from "vitest";
import {
  BackendNotAnnouncedError,
  addressForMessage,
  apiBase,
  authHeaders,
  isDesktop,
  logPath,
} from "./connection";

// No declare global here: connection.ts declares the field, and a global
// declaration in any module covers the whole project.

afterEach(() => {
  delete globalThis.__ZAMLR__;
  delete globalThis.__TAURI_INTERNALS__;
});

describe("connection", () => {
  it("uses the dev server as the default address", () => {
    expect(apiBase()).toBe("http://localhost:8000");
  });

  it("prefers the injected address", () => {
    globalThis.__ZAMLR__ = { apiBase: "https://example.test:54321" };

    expect(apiBase()).toBe("https://example.test:54321");
  });

  it("sends no token header when no token was injected", () => {
    globalThis.__ZAMLR__ = { apiBase: "https://example.test:54321" };

    expect(authHeaders()).not.toHaveProperty("X-Zamlr-Token");
  });

  it("puts the injected token in the token header", () => {
    globalThis.__ZAMLR__ = { token: "test-token" };

    expect(authHeaders()).toMatchObject({
      "X-Zamlr-Token": "test-token",
    });
  });

  it("answers null when no log file was injected", () => {
    expect(logPath()).toBeNull();
  });

  it("answers the injected log file", () => {
    globalThis.__ZAMLR__ = { logPath: String.raw`C:\Users\x\music-zamlr.log` };

    expect(logPath()).toBe(String.raw`C:\Users\x\music-zamlr.log`);
  });

  it("is not the desktop app in a browser", () => {
    expect(isDesktop()).toBe(false);
  });

  it("is the desktop app when Tauri's own global is there", () => {
    // Tauri's global, which exists before any script of the page runs.
    // Ours arrives a second later, when the backend announces its port,
    // and a component asking for it renders "browser" and never changes.
    globalThis.__TAURI_INTERNALS__ = {};

    expect(isDesktop()).toBe(true);
  });

  it("refuses to guess an address inside the shell", () => {
    globalThis.__TAURI_INTERNALS__ = {};

    // Not the dev-server fallback: with anything listening on 8000 the
    // window would quietly use it instead of the backend it started, and
    // show that database's collections over its own.
    expect(() => apiBase()).toThrow(BackendNotAnnouncedError);
  });

  it("uses the injected address inside the shell", () => {
    globalThis.__TAURI_INTERNALS__ = {};
    globalThis.__ZAMLR__ = { apiBase: "http://127.0.0.1:54321" };

    expect(apiBase()).toBe("http://127.0.0.1:54321");
  });

  it("names the state rather than throwing while writing a message", () => {
    globalThis.__TAURI_INTERNALS__ = {};

    expect(addressForMessage()).toBe("the backend this app starts");
  });
});
