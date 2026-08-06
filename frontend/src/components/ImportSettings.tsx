import { useState } from "react";
import {
  Alert,
  Button,
  FormControl,
  FormControlLabel,
  FormLabel,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import type {
  ImportSettingsValues,
  StructureMode,
  UpgradeAction,
} from "../types";

interface ImportSettingsProps {
  disabled: boolean;
  loading: boolean;
  error: string | null;
  onPreview: (settings: ImportSettingsValues) => void;
}

export function ImportSettings({
  disabled,
  loading,
  error,
  onPreview,
}: ImportSettingsProps) {
  const [destinationRoot, setDestinationRoot] = useState("");
  const [structureMode, setStructureMode] = useState<StructureMode>("mirror");
  const [upgradeAction, setUpgradeAction] =
    useState<UpgradeAction>("keep_both");

  return (
    <Stack spacing={2}>
      <TextField
        label="Destination folder"
        value={destinationRoot}
        onChange={(e) => setDestinationRoot(e.target.value)}
        placeholder="D:\Music"
        fullWidth
      />
      <FormControl>
        <FormLabel>Folder structure</FormLabel>
        <RadioGroup
          row
          value={structureMode}
          onChange={(e) => setStructureMode(e.target.value as StructureMode)}
        >
          <FormControlLabel
            value="mirror"
            control={<Radio />}
            label="Mirror their folders"
          />
          <FormControlLabel
            value="flat"
            control={<Radio />}
            label="All in one folder"
          />
        </RadioGroup>
      </FormControl>
      <FormControl>
        <FormLabel>Upgrade action</FormLabel>
        <RadioGroup
          value={upgradeAction}
          onChange={(e) => setUpgradeAction(e.target.value as UpgradeAction)}
        >
          <FormControlLabel
            sx={{ alignItems: "flex-start", mb: 2 }}
            value="keep_both"
            control={<Radio sx={{ py: 0 }} />}
            label={
              <>
                <Typography variant="body2">Keep both tracks</Typography>
                <Typography variant="caption" color="text.secondary">
                  Your file stays where it is; theirs is added alongside it.
                </Typography>
              </>
            }
          />
          <FormControlLabel
            sx={{ alignItems: "flex-start", mb: 2 }}
            value="move"
            control={<Radio sx={{ py: 0 }} />}
            label={
              <>
                <Typography variant="body2">Move my track aside</Typography>
                <Typography variant="caption" color="text.secondary">
                  Your file moves to a <code>_superseded</code> folder under the
                  destination. You can put it back.
                </Typography>
              </>
            }
          />
          <FormControlLabel
            sx={{ alignItems: "flex-start", mb: 2 }}
            value="delete"
            control={<Radio sx={{ py: 0 }} />}
            label={
              <>
                <Typography variant="body2">Delete my track</Typography>
                <Typography variant="caption" color="error">
                  Your file is deleted. This cannot be undone.
                </Typography>
              </>
            }
          />
        </RadioGroup>
      </FormControl>
      {error && <Alert severity="error">{error}</Alert>}
      <Button
        variant="contained"
        disabled={disabled || loading || destinationRoot.trim() === ""}
        onClick={() =>
          onPreview({ destinationRoot, structureMode, upgradeAction })
        }
      >
        {loading ? "Previewing..." : "Preview import"}
      </Button>
    </Stack>
  );
}
