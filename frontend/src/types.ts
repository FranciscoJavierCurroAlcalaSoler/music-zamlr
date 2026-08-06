export interface Track {
  id: number;
  collection_id: number;
  file_path: string;
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

export interface MatchResult {
  missing: Track[];
  upgrade_available: Match[];
  already_have: Match[];
  needs_review: Track[];
  only_in_mine: Track[];
}

export interface Diff {
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
}

export interface OperationResult {
  operation: PlannedOperation;
  status: "success" | "failed" | "skipped";
  error: string | null;
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
}
