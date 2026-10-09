import { useState } from "react";
import {
  Box,
  Dialog,
  DialogContent,
  DialogTitle,
  DialogActions,
  Button,
  FormControlLabel,
  Radio,
  RadioGroup,
  Typography,
} from "@mui/material";
import type { AmbiguousMatch, Candidate, Track } from "../types";
import { bitrate, text } from "../format";

interface ResolveMatchDialogProps {
  ambiguity: AmbiguousMatch | null;
  chosenMineId: number | null | undefined; // undefined = not yet resolved
  claimedElsewhere: Map<number, string>; // mine id → name of the track holding it
  onResolve: (mineId: number | null) => void;
  onCancel: () => void;
}

const NONE_OF_THESE = "none";

function initialValue(chosenMineId: number | null | undefined): string {
  if (chosenMineId === undefined) return ""; // no decision yet
  if (chosenMineId === null) return NONE_OF_THESE;
  return String(chosenMineId);
}

type CandidateState =
  { selectable: true } | { selectable: false; reason: string };

function candidateState(
  candidate: Candidate,
  claimedElsewhere: Map<number, string>,
): CandidateState {
  const claimant = claimedElsewhere.get(candidate.mine.id);
  if (claimant !== undefined) {
    return { selectable: false, reason: `Already chosen for ${claimant}` };
  }
  if (candidate.would_be === "already_have") {
    return {
      selectable: false,
      reason: "You already have this, at equal or better quality",
    };
  }
  return { selectable: true };
}

function candidateSummary(track: Track): string {
  return [
    track.album ?? "Unknown album",
    track.year,
    track.format,
    bitrate(track.bit_rate),
  ]
    .filter(Boolean)
    .join(" · ");
}

export function ResolveMatchDialog({
  ambiguity,
  chosenMineId,
  claimedElsewhere,
  onResolve,
  onCancel,
}: ResolveMatchDialogProps) {
  const [pending, setPending] = useState(initialValue(chosenMineId));

  // After the hook, never before: every hook must run in the same order on
  // every render, so an early return above useState breaks the rules of
  // hooks. Same shape as ImportResultView.
  if (ambiguity === null) return null;

  function handleConfirm() {
    onResolve(pending === NONE_OF_THESE ? null : Number(pending));
  }

  return (
    // `open` unconditionally: the early return above is what closes it.
    <Dialog open onClose={onCancel} maxWidth="md" fullWidth>
      <DialogTitle>Which main file does this replace?</DialogTitle>
      <DialogContent dividers>
        {/* The incoming track first. The dialog asks which file "this" replaces, so
            it has to show what "this" is — otherwise the answer depends on
            remembering the grid row behind the dialog. Artist and title lead
            here because they identify the song; for the candidates below they
            are identical by construction, so those lead with the file name. */}
        <Box sx={{ mb: 3 }}>
          <Typography variant="overline" color="text.secondary">
            Incoming track
          </Typography>
          <Typography variant="body2">
            {text(ambiguity.theirs.artist)} — {text(ambiguity.theirs.title)}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {ambiguity.theirs.file_name} · {candidateSummary(ambiguity.theirs)}
          </Typography>
        </Box>

        <Typography variant="overline" color="text.secondary">
          Main files
        </Typography>
        <RadioGroup
          value={pending}
          onChange={(event) => setPending(event.target.value)}
        >
          {ambiguity.candidates.map((candidate) => {
            const state = candidateState(candidate, claimedElsewhere);
            return (
              <FormControlLabel
                key={candidate.mine.id}
                value={String(candidate.mine.id)}
                disabled={!state.selectable}
                control={<Radio sx={{ py: 0 }} />}
                sx={{ alignItems: "flex-start", mb: 2 }}
                label={
                  <>
                    <Typography variant="body2">
                      {candidate.mine.file_name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {candidateSummary(candidate.mine)}
                      {!state.selectable && ` — ${state.reason}`}
                    </Typography>
                  </>
                }
              />
            );
          })}

          <FormControlLabel
            value={NONE_OF_THESE}
            control={<Radio sx={{ py: 0 }} />}
            sx={{ alignItems: "flex-start" }}
            label={
              <>
                <Typography variant="body2">None of These</Typography>
                <Typography variant="caption" color="text.secondary">
                  Import as a new track. No main file is the same recording.
                </Typography>
              </>
            }
          />
        </RadioGroup>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleConfirm}
          disabled={pending === ""}
        >
          Confirm
        </Button>
      </DialogActions>
    </Dialog>
  );
}
