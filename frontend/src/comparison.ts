/**
 * Whether a comparison on screen has been overtaken by a later change.
 *
 * Its own module rather than a helper inside DiffView, because a component
 * file may export only components: anything else breaks fast refresh, and
 * eslint says so. Pure, so Vitest holds it to each case without a DOM.
 */

/** What was true when a comparison ran, and what is true now. */
export interface ComparisonInputs {
  mine: string | null;
  theirs: string | null;
  order: string | null;
}

/**
 * Two causes, one answer: either collection re-scanned, or the format order
 * saved again. Both change what a comparison would find, and the table can
 * only say so because it recorded these three values when it ran.
 *
 * null for the recorded values means no comparison has run, which is not
 * stale. Equal nulls on either side are not stale either: before any order is
 * saved the timestamp is null and stays null, and a comparison must not be
 * called old because nothing was ever saved.
 *
 * This marks the table, and nothing else. An import recomputes on the server,
 * so an out-of-date table cannot act on what it shows.
 */
export function comparisonIsStale(
  recorded: ComparisonInputs | null,
  current: ComparisonInputs,
): boolean {
  if (recorded === null) return false;
  return (
    recorded.mine !== current.mine ||
    recorded.theirs !== current.theirs ||
    recorded.order !== current.order
  );
}
