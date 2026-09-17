import { describe, expect, it } from "vitest";
import { moveFormat, moveTier } from "./formatOrder";

// Formats named by hand rather than taken from the app's own list: these
// rules are about lists, and a fixture built from the real formats would
// change meaning every time a format is added to the scanner.
const LOSSY = ["MP3", "AAC"];

describe("moveFormat", () => {
  it("moves a format into the tier above when both hold the same kind", () => {
    const tiers = [["FLAC"], ["ALAC", "WAV"]];

    const result = moveFormat(tiers, "ALAC", "up", LOSSY);

    expect(result.tiers).toEqual([["ALAC", "FLAC"], ["WAV"]]);
    expect(result.blocked).toBe(false);
  });

  it("moves a format into the tier below when both hold the same kind", () => {
    const tiers = [["FLAC", "ALAC"], ["WAV"]];

    const result = moveFormat(tiers, "ALAC", "down", LOSSY);

    expect(result.tiers).toEqual([["FLAC"], ["WAV", "ALAC"]]);
  });

  it("starts a new tier when a shared tier is moved out of at the top", () => {
    const tiers = [["FLAC", "ALAC"], ["MP3"]];

    const result = moveFormat(tiers, "ALAC", "up", LOSSY);

    expect(result.tiers).toEqual([["ALAC"], ["FLAC"], ["MP3"]]);
  });

  it("starts a new tier when a shared tier is moved out of at the bottom", () => {
    const tiers = [["FLAC"], ["MP3", "AAC"]];

    const result = moveFormat(tiers, "AAC", "down", LOSSY);

    expect(result.tiers).toEqual([["FLAC"], ["MP3"], ["AAC"]]);
  });

  it("does nothing for a format that is alone in the top tier", () => {
    const tiers = [["FLAC"], ["MP3"]];

    const result = moveFormat(tiers, "FLAC", "up", LOSSY);

    expect(result.tiers).toEqual(tiers);
    expect(result.blocked).toBe(false);
  });

  it("does nothing for a format that is alone in the bottom tier", () => {
    const tiers = [["FLAC"], ["MP3"]];

    const result = moveFormat(tiers, "MP3", "down", LOSSY);

    expect(result.tiers).toEqual(tiers);
  });

  it("refuses to put a lossy format in a tier of lossless ones", () => {
    const tiers = [["FLAC"], ["MP3"]];

    const result = moveFormat(tiers, "MP3", "up", LOSSY);

    expect(result.blocked).toBe(true);
    expect(result.tiers).toEqual(tiers);
  });

  it("refuses to put a lossless format in a tier of lossy ones", () => {
    const tiers = [["FLAC"], ["MP3"]];

    const result = moveFormat(tiers, "FLAC", "down", LOSSY);

    expect(result.blocked).toBe(true);
    expect(result.tiers).toEqual(tiers);
  });

  it("drops a tier that the move empties", () => {
    const tiers = [["FLAC"], ["ALAC"], ["MP3"]];

    const result = moveFormat(tiers, "ALAC", "up", LOSSY);

    expect(result.tiers).toEqual([["ALAC", "FLAC"], ["MP3"]]);
  });

  it("leaves a format that no tier holds alone", () => {
    const tiers = [["FLAC"], ["MP3"]];

    const result = moveFormat(tiers, "OPUS", "up", LOSSY);

    expect(result.tiers).toEqual(tiers);
    expect(result.blocked).toBe(false);
  });

  it("changes nothing in the tiers it was given", () => {
    // The view keeps the old tiers in state until it stores the result. Edited
    // in place, the new order and the old one would be the same array, and
    // React would see no change to render.
    const tiers = [["FLAC", "ALAC"], ["MP3"]];

    moveFormat(tiers, "ALAC", "down", LOSSY);

    expect(tiers).toEqual([["FLAC", "ALAC"], ["MP3"]]);
  });
});

describe("moveTier", () => {
  it("swaps a tier with the one above it", () => {
    const tiers = [["FLAC"], ["ALAC"], ["MP3"]];

    expect(moveTier(tiers, 1, "up")).toEqual([["ALAC"], ["FLAC"], ["MP3"]]);
  });

  it("swaps a tier with the one below it", () => {
    const tiers = [["FLAC"], ["ALAC"], ["MP3"]];

    expect(moveTier(tiers, 1, "down")).toEqual([["FLAC"], ["MP3"], ["ALAC"]]);
  });

  it("puts a lossy tier above a lossless one", () => {
    // The order the server accepts and the editor warns about. No sequence of
    // chip moves reaches it, because every move across the kinds is refused.
    const tiers = [["FLAC"], ["MP3"]];

    expect(moveTier(tiers, 1, "up")).toEqual([["MP3"], ["FLAC"]]);
  });

  it("does nothing for the top tier moved up", () => {
    const tiers = [["FLAC"], ["MP3"]];

    expect(moveTier(tiers, 0, "up")).toEqual(tiers);
  });

  it("does nothing for the bottom tier moved down", () => {
    const tiers = [["FLAC"], ["MP3"]];

    expect(moveTier(tiers, 1, "down")).toEqual(tiers);
  });

  it("does nothing for an index no tier has", () => {
    const tiers = [["FLAC"], ["MP3"]];

    expect(moveTier(tiers, 7, "up")).toEqual(tiers);
    expect(moveTier(tiers, -1, "down")).toEqual(tiers);
  });

  it("changes nothing in the tiers it was given", () => {
    const tiers = [["FLAC"], ["MP3"]];

    moveTier(tiers, 1, "up");

    expect(tiers).toEqual([["FLAC"], ["MP3"]]);
  });
});
