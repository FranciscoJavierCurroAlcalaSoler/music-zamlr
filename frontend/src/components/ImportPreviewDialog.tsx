import {
  Alert,
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
import type { ImportPreview } from "../types";

interface ImportPreviewDialogProps {
  preview: ImportPreview | null;
  destinationRoot: string;
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
  const list =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  return `This will ${list} of your existing files.`;
}

export function ImportPreviewDialog({
  preview,
  destinationRoot,
  onCancel,
  onConfirm,
}: ImportPreviewDialogProps) {
  const counts = preview?.operation_counts;
  const destructive =
    (counts?.delete ?? 0) + (counts?.move ?? 0) + (counts?.overwrites ?? 0);

  return (
    <Dialog open={preview !== null} onClose={onCancel} maxWidth="md" fullWidth>
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
        <Button onClick={onCancel}>Cancel</Button>
        <Button variant="contained" onClick={onConfirm}>
          Import
        </Button>
      </DialogActions>
    </Dialog>
  );
}
