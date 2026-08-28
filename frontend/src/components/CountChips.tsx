import { Chip, Stack } from "@mui/material";
import { formatCount } from "../format";

interface CountChipsProps {
  counts: {
    scanned: number;
    added: number;
    updated: number;
    deleted: number;
    skipped_non_audio: number;
    matched: number;
  };
}

export function CountChips({ counts }: CountChipsProps) {
  const countsArray = [
    { label: "Scanned", value: counts.scanned },
    { label: "Added", value: counts.added },
    { label: "Updated", value: counts.updated },
    { label: "Deleted", value: counts.deleted },
    { label: "Matched", value: counts.matched },
    { label: "Not audio", value: counts.skipped_non_audio },
  ];

  return (
    <Stack
      direction="row"
      spacing={1}
      useFlexGap
      sx={{ mt: 2, flexWrap: "wrap" }}
    >
      {countsArray.map(({ label, value }) => (
        <Chip
          key={label}
          size="small"
          label={`${label}: ${formatCount(value)}`}
        />
      ))}
    </Stack>
  );
}
