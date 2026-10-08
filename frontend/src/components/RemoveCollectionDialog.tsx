import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from "@mui/material";
import type { Collection } from "../types";

interface RemoveCollectionDialogProps {
  // Separate from collection, which stays set after the dialog closes: the
  // dialog fades out over a few hundred milliseconds, and with collection
  // cleared at once the title reads Remove "" for that whole time.
  open: boolean;
  collection: Collection | null;
  removing: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function RemoveCollectionDialog({
  open,
  collection,
  removing,
  onCancel,
  onConfirm,
}: RemoveCollectionDialogProps) {
  return (
    <Dialog open={open} onClose={removing ? undefined : onCancel}>
      <DialogTitle>Remove "{collection?.name}" from Music Zamlr?</DialogTitle>
      <DialogContent>
        {/* "Remove" and never "Delete": the button acts on the list, and a
            user who reads "Delete" next to their music can fear for the
            files. The text says so, and names what is lost. */}
        <DialogContentText>
          The files in {collection?.root_path} stay where they are. Music Zamlr
          forgets what it stored about them, so the next comparison with this
          folder reads every file again.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={removing}>
          Cancel
        </Button>
        <Button
          variant="contained"
          color="error"
          onClick={onConfirm}
          disabled={removing}
        >
          {removing ? "Removing…" : "Remove"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
