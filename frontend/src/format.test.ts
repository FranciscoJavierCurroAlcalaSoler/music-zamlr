import { describe, expect, it } from "vitest";
import {
  bitrate,
  progressPercent,
  shortenPath,
  fileSize,
  unreadableFilesSummary,
} from "./format";

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

describe("progressPercent", () => {
  // The regression. This shipped returning 0, because the multiplication by
  // 100 was missing, and every other case below still looked plausible: 0 of
  // anything is 0, and a finished run rounded to 1. Only a value in the
  // middle of a run tells the two apart, which is why the bar sat empty
  // through an entire comparison without anything failing.
  it("scales to 100, not to 1", () => {
    expect(progressPercent(1240, 3500)).toBe(35);
  });

  it("is 0 before anything is done", () => {
    expect(progressPercent(0, 3500)).toBe(0);
  });

  it("is 100 when everything is done", () => {
    expect(progressPercent(3500, 3500)).toBe(100);
  });

  // 0 of 0 is a collection that has never been scanned, and without the guard
  // it is NaN — which MUI renders as an empty bar plus a console warning
  // rather than as an error, so it would reach a user looking merely stuck.
  it("is 0 rather than NaN when there is nothing to do", () => {
    expect(progressPercent(0, 0)).toBe(0);
  });

  it("rounds to whole numbers in both directions", () => {
    expect(progressPercent(1, 3)).toBe(33);
    expect(progressPercent(2, 3)).toBe(67);
  });
});

describe("fileSize", () => {
  it("formats zero as bytes", () => {
    expect(fileSize(0)).toBe("0 B");
  });

  it("switches unit at the 1024 boundary", () => {
    expect(fileSize(1023)).toBe("1023 B");
    expect(fileSize(1024)).toBe("1 KB");
  });

  it("keeps one decimal from megabytes up", () => {
    expect(fileSize(1024 * 1024)).toBe("1 MB");
    expect(fileSize(1024 * 1024 * 10)).toBe("10 MB");
    expect(fileSize(1024 * 1024 * 10 + 512 * 1024)).toBe("10.5 MB");
    expect(fileSize(1024 * 1024 * 1024)).toBe("1 GB");
  });

  // Free space on a large drive passes a terabyte, so this is the boundary a
  // real destination reaches, not a hypothetical one.
  it("still has a unit above a terabyte", () => {
    expect(fileSize(1024 * 1024 * 1024 * 1024)).toBe("1 TB");
    expect(fileSize(1024 * 1024 * 1024 * 1024 * 8)).toBe("8 TB");
  });
});

describe("unreadableFilesSummary", () => {
  it("uses the singular for one file", () => {
    expect(unreadableFilesSummary(1)).toBe(
      "1 file could not be read, so its track was compared by tags only.",
    );
  });

  it("uses the plural for more than one file", () => {
    expect(unreadableFilesSummary(2)).toBe(
      "2 files could not be read, so their tracks were compared by tags only.",
    );
  });
});

describe("bitrate", () => {
  it("shows kilobits per second", () => {
    expect(bitrate(320000)).toBe("320 kbps");
  });

  it("shows the placeholder for a missing bitrate", () => {
    expect(bitrate(null)).toBe("—");
  });

  // 0 is what the scanner stores when a file reports no bitrate, as a
  // TrueAudio file does. "0 kbps" would claim a measurement.
  it("shows the placeholder for a bitrate of 0", () => {
    expect(bitrate(0)).toBe("—");
  });
});
