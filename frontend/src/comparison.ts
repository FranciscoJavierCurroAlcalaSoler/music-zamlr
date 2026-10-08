/**
 * Whether a comparison on screen has been overtaken by a later change, and
 * which change it was.
 *
 * Its own module rather than a helper inside DiffView, because a component
 * file may export only components: anything else breaks fast refresh, and
 * eslint says so. Pure, so Vitest holds it to each case without a DOM.
 */

/**
 * The times a comparison depends on: when each collection was last scanned,
 * and when the format order was last saved. Recorded when a comparison runs,
 * and read again now.
 */
export interface ComparisonInputs {
  mine: string | null;
  theirs: string | null;
  order: string | null;
}

/** Each change that can make a comparison old. The table is old if any is true. */
export interface StaleCauses {
  removed: boolean;
  chosenOther: boolean;
  rescanned: boolean;
  orderChanged: boolean;
}

/**
 * Which changes made a comparison old, so the banner names the real cause.
 * More than one can be true at once, and then the banner names each.
 *
 * sides says whether each collection is still the same choice, a different one,
 * or no longer present. Only a "same" side can count as re-scanned: a side
 * that is "other" or "removed" always has a different time, so without the
 * guard every removal or new choice would also read as a re-scan.
 *
 * A null recorded value means no comparison has run, which names nothing.
 * Equal nulls name nothing either: before any order is saved its time is null
 * and stays null, and a comparison must not be called old because nothing was
 * ever saved.
 *
 * This marks the table, and nothing else. An import recomputes on the server,
 * so an out-of-date table cannot act on what it shows.
 */
export function staleCauses(
  recorded: ComparisonInputs | null,
  current: ComparisonInputs,
  sides: { mine: SideState; theirs: SideState },
): StaleCauses {
  if (recorded === null)
    return {
      removed: false,
      chosenOther: false,
      rescanned: false,
      orderChanged: false,
    };
  return {
    removed: sides.mine === "removed" || sides.theirs === "removed",
    chosenOther: sides.mine === "other" || sides.theirs === "other",
    rescanned:
      (sides.mine === "same" && current.mine !== recorded.mine) ||
      (sides.theirs === "same" && current.theirs !== recorded.theirs),
    orderChanged: current.order !== recorded.order,
  };
}

/**
 * One side of a comparison now: the picker still holds the collection the
 * table came from ("same"), holds a different one ("other"), or the
 * collection no longer exists ("removed").
 */
export type SideState = "same" | "other" | "removed";

/**
 * What a comparison records when it runs. The times alone cannot tell a
 * re-scan from a different collection, which has a different time too, so
 * the ids are kept beside them.
 */
export interface RecordedComparison {
  mineId: number;
  theirsId: number;
  inputs: ComparisonInputs;
}

/**
 * The state of one side, from the id the comparison used, the id the picker
 * holds now, and the ids of the collections that exist now.
 *
 * Removal is tested first. A removed collection with the picker moved to
 * another one is removed: reading it as "other" would tell the user they
 * chose something, when the collection they compared is gone.
 */
export function sideState(
  recordedId: number,
  pickedId: number | "",
  collectionIds: number[],
): SideState {
  if (!collectionIds.includes(recordedId)) return "removed";
  if (pickedId !== recordedId) return "other";
  return "same";
}
