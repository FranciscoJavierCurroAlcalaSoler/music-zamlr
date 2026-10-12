/**
 * The value types of frontend/src/types.ts, written out so that a test can
 * hold real API answers to them. TypeScript's types are gone at run time,
 * and the wire-contract test pins only key sets, so nothing else notices a
 * number that arrives as a string, or an enum value the interface does not
 * know.
 *
 * Keep each shape equal to its interface in types.ts. A shape lists only the
 * fields the interface declares: a key the backend sends and the interface
 * ignores harms nothing, and the backend's key sets are test_wire_contract's
 * job.
 */

export type Kind = "string" | "number" | "boolean" | "null";

export type Shape =
  | readonly Kind[]
  | { readonly oneOf: readonly string[] }
  | { readonly arrayOf: Shape }
  | { readonly recordOf: Shape }
  | { readonly fields: { readonly [key: string]: Shape } };

const STRING: Shape = ["string"];
const NUMBER: Shape = ["number"];
const STRING_OR_NULL: Shape = ["string", "null"];
const NUMBER_OR_NULL: Shape = ["number", "null"];

export const TRACK: Shape = {
  fields: {
    id: NUMBER,
    collection_id: NUMBER,
    file_path: STRING,
    file_name: STRING,
    artist: STRING_OR_NULL,
    album: STRING_OR_NULL,
    title: STRING_OR_NULL,
    track_number: NUMBER_OR_NULL,
    year: NUMBER_OR_NULL,
    format: STRING_OR_NULL,
    bit_rate: NUMBER_OR_NULL,
    sample_rate: NUMBER_OR_NULL,
    duration: NUMBER_OR_NULL,
  },
};

export const COLLECTION: Shape = {
  fields: {
    id: NUMBER,
    name: STRING,
    root_path: STRING,
    last_scanned_at: STRING_OR_NULL,
  },
};

const MATCH: Shape = { fields: { mine: TRACK, theirs: TRACK } };

export const SCAN_PROGRESS: Shape = {
  fields: {
    scanned: NUMBER,
    added: NUMBER,
    updated: NUMBER,
    deleted: NUMBER,
    skipped_non_audio: NUMBER,
    matched: NUMBER,
    current_path: STRING_OR_NULL,
  },
};

export const SCAN_RESULT: Shape = {
  fields: {
    scanned: NUMBER,
    added: NUMBER,
    updated: NUMBER,
    deleted: NUMBER,
    skipped_non_audio: NUMBER,
    matched: NUMBER,
    unreadable_files: { arrayOf: STRING },
    unreadable_directories: { arrayOf: STRING },
    collection: COLLECTION,
  },
};

export const DIFF_PROGRESS: Shape = {
  fields: {
    theirs_processed_count: NUMBER,
    theirs_count: NUMBER,
    hashed_count: NUMBER,
    fingerprinted_count: NUMBER,
    current_path: STRING_OR_NULL,
  },
};

export const DIFF_RESULT: Shape = {
  fields: {
    match_results: {
      fields: {
        missing: { arrayOf: TRACK },
        upgrade_available: { arrayOf: MATCH },
        already_have: { arrayOf: MATCH },
        needs_review: {
          arrayOf: {
            fields: {
              theirs: TRACK,
              candidates: {
                arrayOf: {
                  fields: {
                    mine: TRACK,
                    would_be: { oneOf: ["upgrade_available", "already_have"] },
                  },
                },
              },
            },
          },
        },
        only_in_mine: { arrayOf: TRACK },
        rejected: {
          arrayOf: {
            fields: { mine: TRACK, theirs: TRACK, error_rate: NUMBER },
          },
        },
        fingerprints_available: ["boolean"],
        unreadable_files: { arrayOf: STRING },
      },
    },
    match_counts: {
      fields: {
        missing: NUMBER,
        upgrade_available: NUMBER,
        already_have: NUMBER,
        needs_review: NUMBER,
        only_in_mine: NUMBER,
      },
    },
  },
};

const PLANNED_OPERATION: Shape = {
  fields: {
    source: STRING,
    destination: STRING_OR_NULL,
    action: { oneOf: ["copy", "delete", "move"] },
    group_id: NUMBER,
    overwrites: ["boolean"],
  },
};

export const IMPORT_PROGRESS: Shape = {
  fields: {
    phase: { oneOf: ["comparing", "copying"] },
    processed_count: NUMBER,
    total_count: NUMBER,
    current_path: STRING_OR_NULL,
  },
};

export const IMPORT_PREVIEW: Shape = {
  fields: {
    operations: { arrayOf: PLANNED_OPERATION },
    upgrades: { arrayOf: MATCH },
    operation_counts: { recordOf: NUMBER },
    bytes_required: NUMBER,
    bytes_free: NUMBER,
  },
};

export const IMPORT_RESULT: Shape = {
  fields: {
    operations: {
      arrayOf: {
        fields: {
          operation: PLANNED_OPERATION,
          status: { oneOf: ["success", "failed", "skipped"] },
          error: STRING_OR_NULL,
        },
      },
    },
    status_counts: { recordOf: NUMBER },
    log_path: STRING_OR_NULL,
    log_error: STRING_OR_NULL,
  },
};

export const FORMAT_ORDER: Shape = {
  fields: {
    tiers: { arrayOf: { arrayOf: STRING } },
    default_tiers: { arrayOf: { arrayOf: STRING } },
    placed: { arrayOf: STRING },
    lossy_formats: { arrayOf: STRING },
    updated_at: STRING_OR_NULL,
  },
};

function kindOf(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

// Array.isArray does not narrow a readonly array type, so TypeScript would
// still see a list of kinds in the branches after this one.
function isKinds(shape: Shape): shape is readonly Kind[] {
  return Array.isArray(shape);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return kindOf(value) === "object";
}

/**
 * Every place where value does not fit shape, one line each, named by its
 * path. An empty list means the value fits. Lines, not a boolean, so that a
 * failing test says which field broke and what arrived instead.
 */
export function problems(value: unknown, shape: Shape, path: string): string[] {
  const found = `${kindOf(value)} ${JSON.stringify(value)}`;
  if (isKinds(shape)) {
    return (shape as readonly string[]).includes(kindOf(value))
      ? []
      : [`${path}: expected ${shape.join(" or ")}, got ${found}`];
  }
  if ("oneOf" in shape) {
    return typeof value === "string" && shape.oneOf.includes(value)
      ? []
      : [`${path}: expected one of ${shape.oneOf.join(", ")}, got ${found}`];
  }
  if ("arrayOf" in shape) {
    if (!Array.isArray(value))
      return [`${path}: expected an array, got ${found}`];
    return value.flatMap((item, index) =>
      problems(item, shape.arrayOf, `${path}[${index}]`),
    );
  }
  if (!isPlainObject(value))
    return [`${path}: expected an object, got ${found}`];
  if ("recordOf" in shape) {
    return Object.entries(value).flatMap(([key, item]) =>
      problems(item, shape.recordOf, `${path}.${key}`),
    );
  }
  return Object.entries(shape.fields).flatMap(([key, fieldShape]) =>
    key in value
      ? problems(value[key], fieldShape, `${path}.${key}`)
      : [`${path}.${key}: missing`],
  );
}
