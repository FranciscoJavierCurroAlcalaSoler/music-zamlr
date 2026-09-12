import { Box, Typography } from "@mui/material";

interface PathListProps {
  paths: string[];
}

/**
 * Long Windows paths, one per line, allowed to break anywhere.
 *
 * Its own file because two views show a list of paths: the scan result and
 * the diff. A second copy can lose the break rule, and a long path then runs
 * past the edge of the page in one view only.
 */
export function PathList({ paths }: PathListProps) {
  return (
    <Box component="ul" sx={{ mt: 1, mb: 0, pl: 3 }}>
      {paths.map((path) => (
        <Typography
          component="li"
          variant="body2"
          key={path}
          sx={{ wordBreak: "break-all" }}
        >
          {path}
        </Typography>
      ))}
    </Box>
  );
}
