import { Box, LinearProgress, Typography } from "@mui/material";
import { CountChips } from "./CountChips";
import { shortenPath } from "../format";
import type { ScanProgress } from "../types";

interface ScanProgressViewProps {
  progress: ScanProgress | null;
}

export function ScanProgressView({ progress }: ScanProgressViewProps) {
  if (progress === null) return null;
  return (
    <Box sx={{ py: 1.5 }}>
      {/* Indeterminate on purpose. A percentage needs a total, and the only
          way to know one is a second walk of the drive that can disagree
          with the real one. DiffProgressView is determinate for exactly the
          opposite reason: the matcher knows how many tracks it will visit
          before it starts. */}
      <LinearProgress sx={{ height: 6, borderRadius: 1 }} />
      {/* CountChips carries its own mt, so the spacing above comes from there
          rather than from the bar, unlike the other two panels. */}
      <CountChips counts={progress} />
      {/* This line is deliberately blank at both ends of a scan: current_path
          is null before the walk starts and again around the stale-row pass.
          minHeight reserves the space, so the chips above do not jump down
          and back up twice per scan. */}
      <Typography
        variant="body2"
        color="text.secondary"
        noWrap
        sx={{ minHeight: "1.5em", mt: 1 }}
      >
        {progress.current_path === null
          ? ""
          : shortenPath(progress.current_path)}
      </Typography>
    </Box>
  );
}
