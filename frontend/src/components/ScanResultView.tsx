import { Alert, Box, Button, Typography } from "@mui/material";
import type { ScanResult } from "../types";
import { pluralize } from "../format";
import { CountChips } from "./CountChips";

interface ScanResultViewProps {
  result: ScanResult | null;
  onDismiss: () => void;
}

/** Long Windows paths, one per line, allowed to break anywhere. */
function PathList({ paths }: { paths: string[] }) {
  return (
    <Box component="ul" sx={{ mt: 1, mb: 0, pl: 3 }}>
      {paths.map((path) => (
        <Typography
          component="li"
          variant="body2"
          key={path}
          sx={{ wordBreak: "break-all" }}
        >
          {path}
        </Typography>
      ))}
    </Box>
  );
}

export function ScanResultView({ result, onDismiss }: ScanResultViewProps) {
  if (result === null) return null;

  const unreadableFiles = result.unreadable_files;
  const unreadableDirectories = result.unreadable_directories;
  const hasProblems =
    unreadableFiles.length > 0 || unreadableDirectories.length > 0;

  // One banner, one severity, computed once. The detail below is plain
  // content rather than more Alerts: an info-coloured box explaining a
  // warning-coloured box reads as "nothing to see here" attached to
  // "something went wrong".
  //
  // Directories lead when both are present. They are the consequential
  // failure: a folder we could not open suppressed deletions, so the scan
  // is incomplete. An unreadable file was merely skipped.
  const problems: string[] = [];
  if (unreadableDirectories.length > 0) {
    problems.push(
      `${pluralize(unreadableDirectories.length, "folder")} could not be opened. Nothing inside was removed.`,
    );
  }
  if (unreadableFiles.length > 0) {
    problems.push(
      `${pluralize(unreadableFiles.length, "file")} could not be read and ${unreadableFiles.length === 1 ? "was" : "were"} skipped.`,
    );
  }

  return (
    <Box sx={{ mt: 2 }}>
      {/* Names the collection: this panel sits under a table of several, and
          otherwise there is nothing saying which row it belongs to. */}
      <Typography variant="h6">
        Scan finished — {result.collection.name}
      </Typography>

      <Alert severity={hasProblems ? "warning" : "success"} sx={{ mt: 1 }}>
        {hasProblems ? problems.join(" ") : "No problems."}
      </Alert>

      <CountChips counts={result} />

      {unreadableDirectories.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">
            Folders that could not be opened
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Nothing was removed from these folders. Tracks recorded inside them
            were kept, because a folder we cannot read is not evidence that its
            files are gone.
          </Typography>
          <PathList paths={unreadableDirectories} />
        </Box>
      )}

      {unreadableFiles.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">
            Files that could not be read
          </Typography>
          <Typography variant="body2" color="text.secondary">
            These were skipped. The rest of the scan completed normally. Check
            them for corruption or permission problems.
          </Typography>
          <PathList paths={unreadableFiles} />
        </Box>
      )}

      <Button onClick={onDismiss} sx={{ mt: 2 }}>
        Done
      </Button>
    </Box>
  );
}
