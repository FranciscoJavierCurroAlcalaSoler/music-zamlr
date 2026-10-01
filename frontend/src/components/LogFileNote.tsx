import { Typography } from "@mui/material";

interface LogFileNoteProps {
  path: string | null;
}

export function LogFileNote({ path }: LogFileNoteProps) {
  if (!path) {
    return null;
  }
  return (
    <Typography variant="body2" sx={{ mt: 1 }}>
      Log file: {path}
    </Typography>
  );
}
