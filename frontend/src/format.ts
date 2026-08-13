/** "1 folder", "3 folders" — so counts never read as "1 folders". */
export function pluralize(
  count: number,
  singular: string,
  plural = `${singular}s`,
): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

// sv-SE is chosen for its format, not its language: it is the locale that
// renders ISO 8601 order (YYYY-MM-DD) with a 24-hour clock.
//
// Constructed once at module load. Intl.DateTimeFormat is expensive enough
// that building one per table row per render is worth avoiding.
const TIMESTAMP_FORMAT = new Intl.DateTimeFormat("sv-SE", {
  dateStyle: "short",
  timeStyle: "short",
});

/**
 * Format a timestamp the backend produced with datetime.now().isoformat().
 *
 * That value is naive local time with no offset, so parsing it as local is
 * correct. Do not format these with toISOString(): it converts to UTC and
 * would display a time shifted by the local offset.
 */
export function formatTimestamp(
  value: string | null,
  fallback = "Never",
): string {
  if (value === null) {
    return fallback;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    // Show the raw value rather than the fallback: "never scanned" and
    // "scanned, but we could not read the timestamp" are different facts.
    return value;
  }
  return TIMESTAMP_FORMAT.format(parsed);
}

const PLACEHOLDER = "—";

export function text(value: string | number | null): string {
  return value === null || value === "" ? PLACEHOLDER : String(value);
}

export function duration(seconds: number | null): string {
  if (seconds === null) return PLACEHOLDER;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

// read_track stores audio.info.bitrate, which is bits per second.
export function bitrate(bitsPerSecond: number | null): string {
  return bitsPerSecond === null
    ? PLACEHOLDER
    : `${Math.round(bitsPerSecond / 1000)} kbps`;
}

/**
 * The last two segments of a path: "D:\Music\Radiohead\Creep.mp3" becomes
 * "Radiohead\Creep.mp3".
 *
 * Slices the original string rather than splitting it and joining it back
 * together, so the separators survive exactly as they were and none has to be
 * guessed. Rejoining would need to know which separator the path used, and
 * there is no safe test for that: a backslash is a legal character inside a
 * Linux filename, so finding one does not make a path a Windows path.
 *
 * A path with fewer than two separators is returned unchanged.
 */
export function shortenPath(path: string): string {
  const lastIndex = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  if (lastIndex <= 0) return path;
  const head = path.slice(0, lastIndex);
  const previousIndex = Math.max(head.lastIndexOf("\\"), head.lastIndexOf("/"));
  if (previousIndex === -1) return path;
  return path.slice(previousIndex + 1);
}
