import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControlLabel,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { ImportResult } from "../types";

interface ImportResultViewProps {
  result: ImportResult | null;
  onDismiss: () => void;
}

export function ImportResultView({ result, onDismiss }: ImportResultViewProps) {
  const [failuresOnly, setFailuresOnly] = useState(false);

  if (result === null) return null;

  const counts = result.status_counts;
  const hasProblems = (counts.failed ?? 0) + (counts.skipped ?? 0) > 0;
  const visible = failuresOnly
    ? result.operations.filter((op) => op.status !== "success")
    : result.operations;

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="h6">Import finished</Typography>

      {hasProblems ? (
        <Alert severity="warning" sx={{ mt: 1 }}>
          {counts.success} succeeded, {counts.failed} failed, {counts.skipped}{" "}
          skipped.
          {(counts.skipped ?? 0) > 0 &&
            " Skipped operations belong to a track whose copy failed, so nothing was deleted or moved for it."}
        </Alert>
      ) : (
        <Alert severity="success" sx={{ mt: 1 }}>
          All {counts.success} operations completed.
        </Alert>
      )}

      {result.log_path && (
        <Typography variant="body2" sx={{ mt: 1 }}>
          Log written to {result.log_path}
        </Typography>
      )}
      {result.log_error && (
        <Alert severity="info" sx={{ mt: 1 }}>
          The import finished, but the log could not be written:{" "}
          {result.log_error}
        </Alert>
      )}

      {hasProblems && (
        <FormControlLabel
          control={
            <Switch
              checked={failuresOnly}
              onChange={(e) => setFailuresOnly(e.target.checked)}
            />
          }
          label="Show problems only"
        />
      )}

      <Table size="small" sx={{ mt: 2 }}>
        <TableHead>
          <TableRow>
            <TableCell>Status</TableCell>
            <TableCell>Action</TableCell>
            <TableCell>File</TableCell>
            <TableCell>Detail</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {visible.map((op, index) => (
            <TableRow key={index}>
              <TableCell>
                <Chip
                  label={op.status}
                  size="small"
                  color={
                    op.status === "success"
                      ? "success"
                      : op.status === "failed"
                        ? "error"
                        : "default"
                  }
                />
              </TableCell>
              <TableCell>{op.operation.action}</TableCell>
              <TableCell sx={{ wordBreak: "break-all" }}>
                {op.operation.source.split(/[\\/]/).pop()}
              </TableCell>
              <TableCell sx={{ wordBreak: "break-all" }}>
                {op.status === "skipped"
                  ? "not attempted"
                  : (op.error ?? op.operation.destination ?? "")}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Button onClick={onDismiss} sx={{ mt: 2 }}>
        Done
      </Button>
    </Box>
  );
}
