import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Chip,
} from "@mui/material";
import type { ImportPreview, Match } from "../types";
import { text, duration, bitrate } from "../format";

interface ImportPreviewDialogProps {
  preview: ImportPreview | null;
  destinationRoot: string;
  executing: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

function relativeTo(root: string, path: string): string {
  // The backend normalizes with os.path.normpath, which emits the server's
  // separator: backslashes on Windows, forward slashes elsewhere. The user
  // may also have typed either. Unify only for comparison, then slice the
  // original so the displayed path keeps the server's separators.
  const unify = (s: string) => s.replace(/\\/g, "/");
  const normalizedRoot = unify(root).replace(/\/+$/, "");
  if (
    !unify(path)
      .toLowerCase()
      .startsWith(normalizedRoot.toLowerCase() + "/")
  ) {
    return path;
  }
  return path.slice(normalizedRoot.length + 1);
}

function describeDestructive(counts: Record<string, number>): string {
  const parts: string[] = [];
  if (counts.delete) parts.push(`delete ${counts.delete}`);
  if (counts.move) parts.push(`move aside ${counts.move}`);
  if (counts.overwrites) parts.push(`overwrite ${counts.overwrites}`);
  if (parts.length === 0) return "";
  const list =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  return `This will ${list} of your existing files.`;
}

interface ComparisonRow {
  label: string;
  mine: string;
  theirs: string;
  flagWhenDifferent: boolean;
}

function comparisonRows(match: Match): ComparisonRow[] {
  const { mine, theirs } = match;
  return [
    // Identity fields: a difference here is the remaster/different-release
    // tell, so it gets flagged.
    {
      label: "Title",
      mine: text(mine.title),
      theirs: text(theirs.title),
      flagWhenDifferent: true,
    },
    {
      label: "Artist",
      mine: text(mine.artist),
      theirs: text(theirs.artist),
      flagWhenDifferent: true,
    },
    {
      label: "Album",
      mine: text(mine.album),
      theirs: text(theirs.album),
      flagWhenDifferent: true,
    },
    {
      label: "Year",
      mine: text(mine.year),
      theirs: text(theirs.year),
      flagWhenDifferent: true,
    },
    // Quality fields: these are *expected* to differ — that is what makes it
    // an upgrade — so flagging them would be noise on every row.
    {
      label: "Duration",
      mine: duration(mine.duration),
      theirs: duration(theirs.duration),
      flagWhenDifferent: false,
    },
    {
      label: "Format",
      mine: text(mine.format),
      theirs: text(theirs.format),
      flagWhenDifferent: false,
    },
    {
      label: "Bitrate",
      mine: bitrate(mine.bit_rate),
      theirs: bitrate(theirs.bit_rate),
      flagWhenDifferent: false,
    },
  ];
}

export function ImportPreviewDialog({
  preview,
  destinationRoot,
  executing,
  onCancel,
  onConfirm,
}: ImportPreviewDialogProps) {
  const counts = preview?.operation_counts;
  const destructive =
    (counts?.delete ?? 0) + (counts?.move ?? 0) + (counts?.overwrites ?? 0);

  return (
    <Dialog
      open={preview !== null}
      onClose={executing ? undefined : onCancel}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle>Confirm import</DialogTitle>
      <DialogContent dividers>
        {counts && (
          <>
            <Typography variant="body1">
              {counts.copy} file{counts.copy === 1 ? "" : "s"} will be copied.
            </Typography>

            {destructive > 0 ? (
              <Alert severity="warning" sx={{ mt: 2 }}>
                {describeDestructive(counts)}
              </Alert>
            ) : (
              <Alert severity="success" sx={{ mt: 2 }}>
                Nothing of yours will be deleted or overwritten.
              </Alert>
            )}
          </>
        )}

        {preview && preview.upgrades.length > 0 && (
          <Box sx={{ mt: 3 }}>
            <Typography variant="subtitle1">
              Files being replaced ({preview.upgrades.length})
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Check that each pair is the same recording. A differing album or
              year often means a remaster or another release.
            </Typography>

            {preview.upgrades.map((match) => (
              <Table key={match.theirs.id} size="small" sx={{ mt: 2 }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ width: "20%" }} />
                    <TableCell sx={{ width: "40%" }}>Yours</TableCell>
                    <TableCell sx={{ width: "40%" }}>Theirs</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {comparisonRows(match).map((row) => {
                    const differs =
                      row.flagWhenDifferent && row.mine !== row.theirs;
                    return (
                      <TableRow key={row.label}>
                        <TableCell>
                          {row.label}
                          {differs && (
                            <Chip
                              label="differs"
                              size="small"
                              color="warning"
                              variant="outlined"
                              sx={{ ml: 1 }}
                            />
                          )}
                        </TableCell>
                        <TableCell>{row.mine}</TableCell>
                        <TableCell>{row.theirs}</TableCell>
                      </TableRow>
                    );
                  })}
                  <TableRow>
                    <TableCell>Your file</TableCell>
                    <TableCell colSpan={2} sx={{ wordBreak: "break-all" }}>
                      {match.mine.file_path}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            ))}
          </Box>
        )}

        {preview && (
          <Table size="small" sx={{ mt: 2 }}>
            <TableHead>
              <TableRow>
                <TableCell>Action</TableCell>
                <TableCell>File</TableCell>
                <TableCell>Destination</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {preview.operations.map((op, index) => (
                <TableRow key={index}>
                  <TableCell>
                    <Chip
                      label={op.action}
                      size="small"
                      color={
                        op.action !== "copy" || op.overwrites
                          ? "warning"
                          : "default"
                      }
                    />
                    {op.overwrites && (
                      <Chip
                        label="replaces yours"
                        size="small"
                        color="error"
                        sx={{ ml: 0.5 }}
                      />
                    )}
                  </TableCell>
                  <TableCell sx={{ wordBreak: "break-all" }}>
                    {op.source.split(/[\\/]/).pop()}
                  </TableCell>
                  <TableCell sx={{ wordBreak: "break-all" }}>
                    {op.destination === null ? (
                      <Typography variant="body2" color="error">
                        deleted
                      </Typography>
                    ) : (
                      relativeTo(destinationRoot, op.destination)
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={executing}>
          Cancel
        </Button>
        <Button variant="contained" onClick={onConfirm} disabled={executing}>
          {executing ? "Importing…" : "Import"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
