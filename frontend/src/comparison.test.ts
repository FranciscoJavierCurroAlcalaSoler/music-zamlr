import { describe, expect, it } from "vitest";
import { sideState, staleCauses } from "./comparison";

// Plain strings, never dates: the rule asks whether two values differ, not
// which of them is later.
const RAN_AT = { mine: "scan-1", theirs: "scan-1", order: "order-1" };
const SAME = { mine: "same", theirs: "same" } as const;

describe("staleCauses", () => {
  it("names nothing while nothing has changed", () => {
    expect(staleCauses(RAN_AT, RAN_AT, SAME)).toEqual({
      removed: false,
      rescanned: false,
      orderChanged: false,
      chosenOther: false,
    });
  });

  it("names nothing when no comparison ran", () => {
    expect(staleCauses(null, RAN_AT, SAME)).toEqual({
      removed: false,
      rescanned: false,
      orderChanged: false,
      chosenOther: false,
    });
  });

  it("names a re-scan of mine", () => {
    expect(staleCauses(RAN_AT, { ...RAN_AT, mine: "scan-2" }, SAME)).toEqual({
      removed: false,
      rescanned: true,
      orderChanged: false,
      chosenOther: false,
    });
  });

  it("names a re-scan of theirs", () => {
    expect(staleCauses(RAN_AT, { ...RAN_AT, theirs: "scan-2" }, SAME)).toEqual({
      removed: false,
      rescanned: true,
      orderChanged: false,
      chosenOther: false,
    });
  });

  it("names a changed format order alone", () => {
    expect(staleCauses(RAN_AT, { ...RAN_AT, order: "order-2" }, SAME)).toEqual({
      removed: false,
      rescanned: false,
      orderChanged: true,
      chosenOther: false,
    });
  });

  it("names the first order ever saved", () => {
    const recorded = { ...RAN_AT, order: null };

    expect(staleCauses(recorded, RAN_AT, SAME)).toEqual({
      removed: false,
      rescanned: false,
      orderChanged: true,
      chosenOther: false,
    });
  });

  it("names nothing while no order has ever been saved", () => {
    const recorded = { ...RAN_AT, order: null };

    expect(staleCauses(recorded, recorded, SAME)).toEqual({
      removed: false,
      rescanned: false,
      orderChanged: false,
      chosenOther: false,
    });
  });

  it("names a removed mine as removed, not as re-scanned", () => {
    const current = { mine: null, theirs: "scan-1", order: "order-1" };

    expect(
      staleCauses(RAN_AT, current, { mine: "removed", theirs: "same" }),
    ).toEqual({
      removed: true,
      rescanned: false,
      orderChanged: false,
      chosenOther: false,
    });
  });

  it("names a removed theirs as removed, not as re-scanned", () => {
    const current = { mine: "scan-1", theirs: null, order: "order-1" };

    expect(
      staleCauses(RAN_AT, current, { mine: "same", theirs: "removed" }),
    ).toEqual({
      removed: true,
      rescanned: false,
      orderChanged: false,
      chosenOther: false,
    });
  });

  it("still names a re-scan of the side that remains", () => {
    const current = { mine: null, theirs: "scan-2", order: "order-1" };

    expect(
      staleCauses(RAN_AT, current, { mine: "removed", theirs: "same" }),
    ).toEqual({
      removed: true,
      rescanned: true,
      orderChanged: false,
      chosenOther: false,
    });
  });

  it("names another chosen mine as chosen, not as re-scanned", () => {
    const current = { mine: "scan-2", theirs: "scan-1", order: "order-1" };

    expect(
      staleCauses(RAN_AT, current, { mine: "other", theirs: "same" }),
    ).toEqual({
      removed: false,
      rescanned: false,
      orderChanged: false,
      chosenOther: true,
    });
  });

  it("names another chosen theirs as chosen, not as re-scanned", () => {
    const current = { mine: "scan-1", theirs: "scan-2", order: "order-1" };

    expect(
      staleCauses(RAN_AT, current, { mine: "same", theirs: "other" }),
    ).toEqual({
      removed: false,
      rescanned: false,
      orderChanged: false,
      chosenOther: true,
    });
  });
});

describe("sideState", () => {
  it("is same when the picker shows the recorded collection", () => {
    expect(sideState(1, 1, [1, 2])).toBe("same");
  });

  it("is other when the picker shows a different collection", () => {
    expect(sideState(1, 2, [1, 2])).toBe("other");
  });

  it("is removed when the recorded collection is gone", () => {
    expect(sideState(1, 1, [2])).toBe("removed");
  });

  it("is removed, not other, when the recorded collection is gone and the picker shows another", () => {
    expect(sideState(1, 2, [2])).toBe("removed");
  });
});
