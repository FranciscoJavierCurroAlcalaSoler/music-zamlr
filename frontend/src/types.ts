export interface Track {
  id: number;
  collection_id: number;
  file_path: string;
  file_name: string;
  artist: string | null;
  album: string | null;
  title: string | null;
  track_number: number | null;
  year: number | null;
  format: string | null;
  bit_rate: number | null;
  sample_rate: number | null;
  duration: number | null;
}

export interface Collection {
  id: number;
  name: string;
  root_path: string;
  last_scanned_at: string | null;
}

export interface Match {
  mine: Track;
  theirs: Track;
}

export interface RejectedMatch {
  mine: Track;
  theirs: Track;
  error_rate: number;
}

export interface ScanProgress {
  scanned: number;
  added: number;
  updated: number;
  deleted: number;
  skipped_non_audio: number;
  matched: number;
  current_path: string | null;
}

export interface ScanResult {
  scanned: number;
  added: number;
  updated: number;
  deleted: number;
  skipped_non_audio: number;
  matched: number;
  unreadable_files: string[];
  unreadable_directories: string[];
  collection: Collection;
}

export type WouldBe = "upgrade_available" | "already_have";

export interface Candidate {
  mine: Track;
  would_be: WouldBe;
}

export interface AmbiguousMatch {
  theirs: Track;
  candidates: Candidate[];
}

export interface TrackResolution {
  theirs_id: number;
  mine_id: number | null;
}

export interface MatchResult {
  missing: Track[];
  upgrade_available: Match[];
  already_have: Match[];
  needs_review: AmbiguousMatch[];
  only_in_mine: Track[];
  rejected: RejectedMatch[];
  fingerprints_available: boolean;
  unreadable_files: string[];
}

export interface DiffProgress {
  theirs_processed_count: number;
  theirs_count: number;
  hashed_count: number;
  fingerprinted_count: number;
  current_path: string | null;
}

export interface DiffResult {
  match_results: MatchResult;
  match_counts: {
    missing: number;
    upgrade_available: number;
    already_have: number;
    needs_review: number;
    only_in_mine: number;
  };
}

export type StructureMode = "mirror" | "flat";
export type UpgradeAction = "delete" | "keep_both" | "move";

export interface ImportSettingsValues {
  destinationRoot: string;
  structureMode: StructureMode;
  upgradeAction: UpgradeAction;
}

export interface PlannedOperation {
  source: string;
  destination: string | null;
  action: "copy" | "delete" | "move";
  group_id: number;
  overwrites: boolean;
}

export interface ImportPreview {
  operations: PlannedOperation[];
  upgrades: Match[];
  operation_counts: Record<string, number>;
  bytes_required: number;
  bytes_free: number;
}

export interface OperationResult {
  operation: PlannedOperation;
  status: "success" | "failed" | "skipped";
  error: string | null;
}

export interface ImportProgress {
  phase: "comparing" | "copying";
  processed_count: number;
  total_count: number;
  current_path: string | null;
}

export interface ImportResult {
  operations: OperationResult[];
  status_counts: Record<string, number>;
  log_path: string | null;
  log_error: string | null;
}

export interface ImportRequestBody {
  track_ids: number[];
  mine_collection_id: number;
  theirs_collection_id: number;
  destination_root: string;
  structure_mode: StructureMode;
  upgrade_action: UpgradeAction;
  resolutions: TrackResolution[];
}
