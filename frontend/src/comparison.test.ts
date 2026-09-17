import { describe, expect, it } from "vitest";
import { comparisonIsStale } from "./comparison";

// Plain strings, never dates: the rule asks whether two values differ, not
// which of them is later.
const RAN_AT = { mine: "scan-1", theirs: "scan-1", order: "order-1" };

describe("comparisonIsStale", () => {
  it("is not stale while nothing has changed", () => {
    expect(comparisonIsStale(RAN_AT, { ...RAN_AT })).toBe(false);
  });

  it("is stale when my collection was re-scanned", () => {
    expect(comparisonIsStale(RAN_AT, { ...RAN_AT, mine: "scan-2" })).toBe(true);
  });

  it("is stale when their collection was re-scanned", () => {
    expect(comparisonIsStale(RAN_AT, { ...RAN_AT, theirs: "scan-2" })).toBe(
      true,
    );
  });

  it("is stale when the format order was saved again", () => {
    expect(comparisonIsStale(RAN_AT, { ...RAN_AT, order: "order-2" })).toBe(
      true,
    );
  });

  it("is stale when an order is saved for the first time", () => {
    // Before any save the timestamp is null. The first save gives it a value,
    // and the comparison on screen was ranked by the order before it.
    const ranBeforeAnySave = { ...RAN_AT, order: null };

    expect(
      comparisonIsStale(ranBeforeAnySave, { ...RAN_AT, order: "order-1" }),
    ).toBe(true);
  });

  it("is not stale while no order has ever been saved", () => {
    // Both null, so nothing was saved between the comparison and now. Read as
    // a change, every comparison would carry the warning on a fresh install.
    const noOrder = { ...RAN_AT, order: null };

    expect(comparisonIsStale(noOrder, { ...noOrder })).toBe(false);
  });

  it("is not stale before a comparison has run", () => {
    expect(comparisonIsStale(null, RAN_AT)).toBe(false);
  });
});
