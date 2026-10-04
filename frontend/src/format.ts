// Constructed once at module load, for the same reason as TIMESTAMP_FORMAT
// below: this runs per row and per progress frame.
//
// No locale argument on purpose, so the browser's own decides the separator —
// a German browser shows 1.240 where an English one shows 1,240. These numbers
// are read, never parsed back, so following the reader is right.
const COUNT_FORMAT = new Intl.NumberFormat();

/**
 * "1,240" rather than "1240".
 *
 * Every count in this app can reach four digits: a library of a few thousand
 * tracks is the ordinary case, not the large one, and the separator is what
 * makes 1240 and 12400 tell apart at a glance.
 */
export function formatCount(value: number): string {
  return COUNT_FORMAT.format(value);
}

/**
 * How far through, as a whole number out of 100 for MUI's determinate bars.
 *
 * Zero total is the collection that has never been scanned, and the guard is
 * why this is a function rather than one expression at the call site: 0/0 is
 * NaN, and MUI renders a NaN value as an empty bar with a console warning
 * rather than failing outright.
 *
 * Lives here, not in DiffProgressView, so the arithmetic can be tested
 * without a DOM. A missing multiplication by 100 returns 0 for 1240 of 3500,
 * and nothing short of a long comparison would show it on screen.
 */
export function progressPercent(done: number, total: number): number {
  return total === 0 ? 0 : Math.round((done / total) * 100);
}

/** "1 folder", "3 folders" — so counts never read as "1 folders". */
export function pluralize(
  count: number,
  singular: string,
  plural = `${singular}s`,
): string {
  return `${formatCount(count)} ${count === 1 ? singular : plural}`;
}

/**
 * The first sentence of the diff's warning about files it could not read.
 *
 * It lives here, away from the component, because Vitest runs with no DOM.
 * A sentence built inside the Alert has no automated cover at all.
 *
 * The words name no tier. The list mixes files that the hash tier could not
 * open with files that fpcalc could not read, and with no fpcalc on the
 * machine it holds the first kind only.
 *
 * The verb follows count === 1, the same rule pluralize uses. Two different
 * rules in one sentence disagree at 0: "0 files ... its track was".
 */
export function unreadableFilesSummary(count: number): string {
  return `${pluralize(count, "file")} could not be read, so ${count === 1 ? "its track was" : "their tracks were"} compared by tags only.`;
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

// read_track stores audio.info.bitrate, which is bits per second. It stores 0
// when the file reports no bitrate, as a TrueAudio file does, so 0 shows the
// same placeholder as a missing value, never "0 kbps".
export function bitrate(bitsPerSecond: number | null): string {
  return bitsPerSecond === null || bitsPerSecond === 0
    ? PLACEHOLDER
    : `${Math.round(bitsPerSecond / 1000)} kbps`;
}

/**
 * Base 1024, with Explorer's labels rather than KiB/MiB. Deliberate: this
 * number exists to be compared against what Windows shows in the properties
 * dialog of the drive being filled, and decimal units read about 7% smaller
 * for the same drive, which would make the warning look wrong.
 *
 * Ends at TB rather than continuing, because free space on a large drive
 * passes a terabyte and "3835.6 GB" is not a quantity anyone reads.
 */
export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${Math.round((bytes / (1024 * 1024)) * 10) / 10} MB`;
  if (bytes < 1024 * 1024 * 1024 * 1024)
    return `${Math.round((bytes / (1024 * 1024 * 1024)) * 10) / 10} GB`;
  return `${Math.round((bytes / (1024 * 1024 * 1024 * 1024)) * 10) / 10} TB`;
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
