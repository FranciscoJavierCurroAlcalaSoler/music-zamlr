export interface Track {
  id: number;
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