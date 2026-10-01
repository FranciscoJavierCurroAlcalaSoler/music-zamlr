import { afterEach, describe, expect, it } from "vitest";
import { apiBase, authHeaders, logPath } from "./connection";

// No declare global here: connection.ts declares the field, and a global
// declaration in any module covers the whole project.

afterEach(() => {
  delete globalThis.__ZAMLR__;
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
});
