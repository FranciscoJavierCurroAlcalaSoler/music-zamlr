import {
  Alert, Button, Dialog, DialogActions, DialogContent,
  DialogTitle, Typography,
} from '@mui/material';
import type { ImportPreview } from '../types';

interface ImportPreviewDialogProps {
  preview: ImportPreview | null;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ImportPreviewDialog({ preview, onCancel, onConfirm }: ImportPreviewDialogProps) {
  const counts = preview?.operation_counts;
  const destructive = (counts?.delete ?? 0) + (counts?.move ?? 0) + (counts?.overwrites ?? 0);

  return (
    <Dialog open={preview !== null} onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle>Confirm import</DialogTitle>
      <DialogContent dividers>
          {counts && (
            <>
                <Typography variant="body1">
                {counts.copy} file{counts.copy === 1 ? '' : 's'} will be copied.
                </Typography>

                {destructive > 0 ? (
                <Alert severity="warning" sx={{ mt: 2 }}>
                    This will also delete {counts.delete}, move aside {counts.move}, and
                    overwrite {counts.overwrites} of your existing files.
                </Alert>
                ) : (
                <Alert severity="success" sx={{ mt: 2 }}>
                    Nothing of yours will be deleted or overwritten.
                </Alert>
                )}
            </>
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