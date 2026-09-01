import { Box, LinearProgress, Stack, Typography } from "@mui/material";
import { formatCount, progressPercent, shortenPath } from "../format";
import type { ImportProgress } from "../types";

interface ImportProgressViewProps {
  progress: ImportProgress | null;
}

function describePhase(phase: ImportProgress["phase"]): string {
  if (phase === "comparing") {
    return "Comparing again before anything is written — nothing on disk has changed yet.";
  }
  // Checked rather than assumed, as in describeStatus: a third phase would
  // break the build here instead of falling through to the copying wording,
  // which is the one that tells someone their library is being modified.
  phase satisfies "copying";
  return "Copying files — your library is being changed now.";
}

/**
 * Progress for both import endpoints, which is why it names its phase.
 *
 * A preview only ever compares. An execute compares first — recomputing the
 * whole diff, because the server never trusts a client-supplied
 * classification — and only then copies. So pressing Import and watching a
 * comparison run is correct and surprising at the same time, and the wording
 * is there to say so rather than leaving the user to guess.
 *
 * The phase line goes above the counts, not below: it is the frame those
 * numbers are read through. total_count drops between the two phases, from
 * tracks compared to operations planned, so the bar jumps backwards partway
 * through an import. The phase is what stops that looking like a fault.
 */
export function ImportProgressView({ progress }: ImportProgressViewProps) {
  if (progress === null) return null;
  return (
    // Its own padding, because this sits outside DialogContent and inherits
    // none. px matches DialogContent's so the text lines up with the table
    // above rather than starting at the dialog's edge.
    <Box sx={{ px: 3, py: 1.5 }}>
      <LinearProgress
        variant="determinate"
        value={progressPercent(progress.processed_count, progress.total_count)}
        sx={{ height: 6, borderRadius: 1, mb: 1 }}
      />
      {/* Message and count on one row: the count is a detail of the sentence
          beside it, not a statement of its own. flexShrink stops a long phase
          message from squeezing "67 of 557" onto two lines. */}
      <Stack
        direction="row"
        spacing={2}
        sx={{ justifyContent: "space-between", alignItems: "baseline" }}
      >
        <Typography variant="body2">{describePhase(progress.phase)}</Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ flexShrink: 0 }}
        >
          {formatCount(progress.processed_count)} of{" "}
          {formatCount(progress.total_count)}
        </Typography>
      </Stack>
      {/* Blank while the phase turns over and at the end of a run, so the
          height is reserved rather than letting the line collapse. Secondary
          and truncated: it changes several times a second, and it is the
          least important of the three. */}
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
