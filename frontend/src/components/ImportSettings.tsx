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
          row
          value={upgradeAction}
          onChange={(e) => setUpgradeAction(e.target.value as UpgradeAction)}
        >
          <FormControlLabel
            value="delete"
            control={<Radio />}
            label="Delete my tracks"
          />
          <FormControlLabel
            value="keep_both"
            control={<Radio />}
            label="Keep both tracks"
          />
          <FormControlLabel
            value="move"
            control={<Radio />}
            label="Move my track to superseded folder"
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
