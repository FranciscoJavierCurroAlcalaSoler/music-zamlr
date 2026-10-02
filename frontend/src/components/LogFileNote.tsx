import { Button, Stack, Typography } from "@mui/material";
import { revealItemInDir } from "@tauri-apps/plugin-opener";

import { isDesktop } from "../connection";

interface LogFileNoteProps {
  path: string | null;
}

export function LogFileNote({ path }: LogFileNoteProps) {
  if (!path) {
    return null;
  }
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 1 }}>
      <Typography variant="body2">Log file: {path}</Typography>
      {/* revealItemInDir takes the file, not its folder, and opens the
          folder with that file selected — which is what somebody being
          asked to send their log needs. Absent in a browser, where it
          would reach the wrong machine. */}
      {isDesktop() && (
        <Button size="small" onClick={() => void revealItemInDir(path)}>
          Open folder
        </Button>
      )}
    </Stack>
  );
}
