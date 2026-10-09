import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";

import { isDesktop } from "../connection";
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

  async function handleBrowse() {
    const picked = await open({
      directory: true,
      multiple: false,
      title: "Choose the destination folder",
    });
    if (typeof picked === "string") {
      setDestinationRoot(picked);
    }
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
        <TextField
          label="Destination folder"
          value={destinationRoot}
          onChange={(e) => setDestinationRoot(e.target.value)}
          placeholder="D:\Music"
          fullWidth
        />
        {isDesktop() && (
          <Button variant="outlined" onClick={handleBrowse}>
            Browse…
          </Button>
        )}
      </Stack>
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
            label="Mirror the incoming folders"
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
                  The main file stays where it is; the incoming file is added
                  beside it.
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
                <Typography variant="body2">
                  Move the replaced file aside
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  The main file moves to a <code>_superseded</code> folder under
                  the destination. You can put it back.
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
                <Typography variant="body2">
                  Delete the replaced file
                </Typography>
                <Typography variant="caption" color="error">
                  The main file is deleted. This cannot be undone.
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
