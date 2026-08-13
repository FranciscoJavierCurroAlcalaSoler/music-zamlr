import { describe, expect, it } from "vitest";
import { shortenPath } from "./format";

// A real backslash, built rather than typed. A literal "\M" in a TS string is
// not an escape sequence, so the compiler silently drops the backslash and the
// test then asserts against a path that has none.
const B = String.fromCharCode(92);

describe("shortenPath", () => {
  it("keeps the last two segments of a Windows path", () => {
    expect(shortenPath(`D:${B}Music${B}Radiohead${B}Creep.mp3`)).toBe(
      `Radiohead${B}Creep.mp3`,
    );
  });

  it("keeps the last two segments of a POSIX path", () => {
    expect(shortenPath("/home/curro/music/Radiohead/Creep.mp3")).toBe(
      "Radiohead/Creep.mp3",
    );
  });

  it("preserves non-ASCII characters", () => {
    expect(shortenPath(`D:${B}Music${B}Sigur Rós${B}Hoppípolla.flac`)).toBe(
      `Sigur Rós${B}Hoppípolla.flac`,
    );
  });

  // The case that decided the implementation. Splitting the path and rejoining
  // it would have to guess which separator to use, and a backslash is a legal
  // character inside a Linux filename, so guessing turns this filename into a
  // directory. Slicing the original string cannot get it wrong.
  it("does not treat a backslash inside a POSIX filename as a separator", () => {
    expect(shortenPath(`/home/curro/weird${B}name.mp3`)).toBe(
      `weird${B}name.mp3`,
    );
  });

  it("returns a path that is already two segments unchanged", () => {
    expect(shortenPath(`Radiohead${B}Creep.mp3`)).toBe(
      `Radiohead${B}Creep.mp3`,
    );
  });

  it("returns a bare filename unchanged", () => {
    expect(shortenPath("Creep.mp3")).toBe("Creep.mp3");
  });

  it("returns a single leading separator unchanged", () => {
    expect(shortenPath("/Creep.mp3")).toBe("/Creep.mp3");
  });

  it("returns a drive-root path unchanged", () => {
    expect(shortenPath(`D:${B}Creep.mp3`)).toBe(`D:${B}Creep.mp3`);
  });
});
