import { Box, LinearProgress, Stack, Typography } from "@mui/material";
import { formatCount, progressPercent, shortenPath } from "../format";
import type { DiffProgress } from "../types";

interface DiffProgressViewProps {
  progress: DiffProgress | null;
}

/**
 * Determinate, unlike ScanProgressView, and the difference is not a matter of
 * taste: theirs_count is fixed before the matcher does any work, while os.walk
 * can never know how many files a scan will find.
 *
 * The count is honest and the time is not. An iteration with no same-size
 * candidate is a dictionary lookup, and one with a candidate hashes whole
 * files, so the bar advances in lurches and then sits still through a large
 * FLAC. hashed_count is what explains a stalled bar, which is why it is on
 * screen next to it.
 *
 * CountChips is deliberately not reused here. Its prop is the six scan
 * counters, and these are three unrelated numbers. Widening it to an arbitrary
 * list of labels would push that six-item array back into both scan callers,
 * which is the duplication that extracting it removed.
 */
export function DiffProgressView({ progress }: DiffProgressViewProps) {
  if (progress === null) return null;
  return (
    <Box sx={{ py: 1.5 }}>
      <LinearProgress
        variant="determinate"
        value={progressPercent(
          progress.theirs_processed_count,
          progress.theirs_count,
        )}
        sx={{ height: 6, borderRadius: 1, mb: 1 }}
      />
      {/* The hash count is the reason the bar stalls, so it belongs beside the
          count it explains rather than under it. flexShrink keeps the pair on
          one line as the numbers grow. */}
      <Stack
        direction="row"
        spacing={2}
        sx={{ justifyContent: "space-between", alignItems: "baseline" }}
      >
        <Typography variant="body2">
          Comparing {formatCount(progress.theirs_processed_count)} of{" "}
          {formatCount(progress.theirs_count)}
        </Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ flexShrink: 0 }}
        >
          {formatCount(progress.hashed_count)} hashed
        </Typography>
      </Stack>
      <Typography
        variant="body2"
        color="text.secondary"
        noWrap
        sx={{ minHeight: "1.5em" }}
      >
        {progress.current_path === null
          ? ""
          : shortenPath(progress.current_path)}
      </Typography>
    </Box>
  );
}
