/**
 * The editing rules for the format order, as one pure function.
 *
 * The order is a list of tiers, best first, and a tier is a list of format
 * names that tie. The Settings view shows one row per tier and moves a format
 * with the buttons on its chip; every move comes through here.
 *
 * No fetch and no React, so Vitest tests it with plain arrays and no DOM. The
 * server owns the real rules and refuses an order that breaks them; this
 * function stops the one move a user makes by accident, so that a warning
 * arrives on the click rather than on Save.
 */

export interface MoveResult {
  tiers: string[][];
  blocked: boolean;
}

/**
 * Swap a tier with the one above or below it.
 *
 * Moving a chip can never carry a format past a tier of the other kind,
 * because such a move is refused. Without this function the editor could not
 * reach an order the server accepts and warns about: a lossy tier above a
 * lossless one. A swap is always allowed, since it moves whole tiers and so
 * cannot make a tier that mixes the two kinds.
 *
 * A tier at the end it is asked to move towards stays where it is, and so
 * does an index no tier has.
 */
export function moveTier(
  tiers: string[][],
  index: number,
  direction: "up" | "down",
): string[][] {
  const targetIndex = direction === "up" ? index - 1 : index + 1;
  if (index < 0 || index >= tiers.length) return tiers;
  if (targetIndex < 0 || targetIndex >= tiers.length) return tiers;

  const result = tiers.map((tier) => [...tier]);
  [result[index], result[targetIndex]] = [result[targetIndex], result[index]];
  return result;
}

/**
 * Move one format up or down a tier, and say whether the rules refused.
 *
 * Returns new arrays and changes nothing in place: React compares by
 * identity, so tiers edited in place would leave the old rows on screen.
 *
 * A move to a tier of the other kind is refused, because a lossy format and a
 * lossless one must never tie: their bitrates measure different things.
 * Refusal is a value rather than a thrown error, since it is an ordinary
 * thing for a user to try.
 */
export function moveFormat(
  tiers: string[][],
  format: string,
  direction: "up" | "down",
  lossyFormats: string[],
): MoveResult {
  const sourceIndex = tiers.findIndex((tier) => tier.includes(format));
  if (sourceIndex === -1) return { tiers, blocked: false };

  const targetIndex = direction === "up" ? sourceIndex - 1 : sourceIndex + 1;
  const sourceTier = tiers[sourceIndex];

  if (targetIndex < 0 || targetIndex >= tiers.length) {
    // Past the end of the list. A format that shares its tier leaves it and
    // starts a tier of its own, which is how it stops tying with the formats
    // beside it. A format already alone there has nowhere to go: a new tier
    // would repeat the one it just left, and the order would look unchanged
    // while every rank below it shifted.
    if (sourceTier.length === 1) return { tiers, blocked: false };

    const result = tiers.map((tier, index) =>
      index === sourceIndex
        ? tier.filter((item) => item !== format)
        : [...tier],
    );
    result.splice(direction === "up" ? 0 : result.length, 0, [format]);
    return { tiers: result, blocked: false };
  }

  // The kind of the target tier comes from the formats in it, not from its
  // position: the user may rank a lossy tier above a lossless one, so nothing
  // about where a tier sits says which kind it holds.
  const formatIsLossy = lossyFormats.includes(format);
  const targetIsLossy = tiers[targetIndex].some((item) =>
    lossyFormats.includes(item),
  );
  if (formatIsLossy !== targetIsLossy) return { tiers, blocked: true };

  const result: string[][] = [];
  tiers.forEach((tier, index) => {
    if (index === sourceIndex) {
      // A tier the move empties disappears. Left in place it would be a row
      // with no chips, and every tier below it would rank one step lower for
      // no reason the user could see.
      const remaining = tier.filter((item) => item !== format);
      if (remaining.length) result.push(remaining);
    } else if (index === targetIndex) {
      // Placed at the end it arrives from, so the chip stays next to where it
      // was. Formats inside a tier tie, so this is display order only.
      result.push(direction === "up" ? [format, ...tier] : [...tier, format]);
    } else {
      result.push([...tier]);
    }
  });
  return { tiers: result, blocked: false };
}
