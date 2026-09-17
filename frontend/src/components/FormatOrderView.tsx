import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  Paper,
  Stack,
  Typography,
} from "@mui/material";

import type { FormatOrder } from "../types";
import { describeFetchError, fetchFormatOrder, saveFormatOrder } from "../api";
import { moveFormat, moveTier } from "../formatOrder";

/**
 * The Settings tab: the order of formats, as one row of chips per tier.
 *
 * The rules live elsewhere, and none of them is repeated here. moveFormat
 * decides what a move does, and the server decides what may be saved; this
 * view fetches, shows, and reports what each of them answers. The kinds come
 * from the server as lossy_formats, because a list of formats written out
 * again in the browser would drift from the scanner as formats are added.
 */
interface FormatOrderViewProps {
  /** Called after a save, so the rest of the app can read the new timestamp. */
  onSaved: () => void;
}

export function FormatOrderView({ onSaved }: FormatOrderViewProps) {
  const [order, setOrder] = useState<FormatOrder | null>(null);
  // The tiers on screen, which are the saved ones until the user moves a
  // chip. Held apart from `order` so that Save has something to send and the
  // saved state stays available to compare against.
  const [tiers, setTiers] = useState<string[][]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);

  // Promise callbacks rather than async/await, as in App.tsx: an effect may
  // not reach a setState synchronously, and to that rule the whole body of an
  // async function counts as synchronous.
  const refresh = useCallback(() => {
    return fetchFormatOrder()
      .then((data) => {
        setOrder(data);
        setTiers(data.tiers);
        setError(null);
      })
      .catch((cause: unknown) => {
        setError(describeFetchError(cause));
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function onMove(format: string, direction: "up" | "down") {
    if (order === null) return;
    const result = moveFormat(tiers, format, direction, order.lossy_formats);
    setTiers(result.tiers);
    setBlocked(
      result.blocked
        ? `${format} cannot share a tier with formats of the other kind. A ` +
            `lossy format and a lossless one never tie, because a bitrate ` +
            `means something different for each.`
        : null,
    );
  }

  // A whole tier moves as one. A chip cannot pass a tier of the other kind,
  // since that move is refused, so this is the only way to reach an order
  // that ranks a lossy tier above a lossless one — which the server allows
  // and the warning below is about.
  function onMoveTier(index: number, direction: "up" | "down") {
    setTiers(moveTier(tiers, index, direction));
    setBlocked(null);
  }

  // The whole order goes to the server at once, not each move. A half-edited
  // order is often illegal — moving one format out of a mixed pair takes two
  // moves — and the server would refuse the state in between.
  function save(tiersToSave: string[][]) {
    setSaving(true);
    setError(null);
    setBlocked(null);
    saveFormatOrder(tiersToSave)
      .then((data) => {
        // The answer, not the request: it carries what a comparison will rank
        // by, and a save of the default order stores nothing at all, so its
        // timestamp comes back empty.
        setOrder(data);
        setTiers(data.tiers);
        // After the answer, never on the click: the timestamp that matters is
        // the one the server wrote, and a refused save wrote none.
        onSaved();
      })
      .catch((cause: unknown) => {
        setError(describeFetchError(cause));
      })
      .finally(() => {
        setSaving(false);
      });
  }

  const lossyFormats = order?.lossy_formats ?? [];
  const isLossyTier = (tier: string[]) =>
    tier.some((format) => lossyFormats.includes(format));
  // A lossy tier anywhere above a tier that is not lossy. The rules allow it,
  // and the user may want it, but it is the arrangement that lets an MP3
  // replace a FLAC, so it is said plainly.
  const lossyAboveLossless = tiers.some(
    (tier, index) =>
      isLossyTier(tier) &&
      tiers.slice(index + 1).some((lower) => !isLossyTier(lower)),
  );
  const unsaved =
    order !== null && JSON.stringify(tiers) !== JSON.stringify(order.tiers);

  if (loading) {
    return <Typography>Loading the format order…</Typography>;
  }

  return (
    <Box sx={{ p: 3, maxWidth: 900 }}>
      <Typography variant="h6">Format order</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        The formats in one tier are equally good. A file in a higher tier is
        better than a file in a lower one, whatever its bitrate.
      </Typography>

      <Stack spacing={1} sx={{ mb: 2 }}>
        {error && <Alert severity="error">{error}</Alert>}
        {blocked && <Alert severity="warning">{blocked}</Alert>}
        {lossyAboveLossless && (
          <Alert severity="warning">
            A lossy tier is above a lossless one. With <b>Delete my track</b>,
            an import can then replace a lossless file with a lossy one.
          </Alert>
        )}
        {/* The list the server sends, never a comparison made here: the server
            is what placed these formats, and only it knows which. */}
        {order !== null && order.placed.length > 0 && (
          <Alert severity="info">
            The app placed {order.placed.join(", ")} in the order for you. Move
            them if you want them somewhere else.
          </Alert>
        )}
      </Stack>

      {/* One card per tier. The tier's own controls sit apart from the chips,
          on the right of its heading, because a button beside a format name
          must clearly belong to that format and not to the whole row. */}
      {tiers.map((tier, index) => (
        <Paper key={index} variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", mb: 1, gap: 1 }}>
            <Typography variant="subtitle2">Tier {index + 1}</Typography>
            <Chip
              size="small"
              variant="outlined"
              label={isLossyTier(tier) ? "lossy" : "lossless"}
              color={isLossyTier(tier) ? "default" : "primary"}
            />
            {index === 0 && (
              <Typography variant="caption" color="text.secondary">
                best
              </Typography>
            )}
            <Box sx={{ flexGrow: 1 }} />
            {/* Worded, not an arrow. The chips carry arrows of their own, and
                two kinds of arrow on one row say nothing about which moves a
                format and which moves the whole tier. */}
            <Button
              size="small"
              onClick={() => onMoveTier(index, "up")}
              disabled={index === 0}
              aria-label={`Move tier ${index + 1} up`}
            >
              ↑ Move tier
            </Button>
            <Button
              size="small"
              onClick={() => onMoveTier(index, "down")}
              disabled={index === tiers.length - 1}
              aria-label={`Move tier ${index + 1} down`}
            >
              ↓ Move tier
            </Button>
          </Box>
          {/* Wraps, because a tier can hold every lossless format at once and
              a single row of them is wider than the window. */}
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            {tier.map((format) => (
              <Box
                key={format}
                sx={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 0.25,
                  pl: 1.5,
                  pr: 0.25,
                  py: 0.25,
                  border: 1,
                  borderColor: "divider",
                  borderRadius: 4,
                  bgcolor: "action.hover",
                }}
              >
                <Typography variant="body2" sx={{ mr: 0.5 }}>
                  {format}
                </Typography>
                <IconButton
                  size="small"
                  onClick={() => onMove(format, "up")}
                  aria-label={`Move ${format} up`}
                  title={`Move ${format} up one tier`}
                  sx={{ width: 24, height: 24, fontSize: 14 }}
                >
                  ↑
                </IconButton>
                <IconButton
                  size="small"
                  onClick={() => onMove(format, "down")}
                  aria-label={`Move ${format} down`}
                  title={`Move ${format} down one tier`}
                  sx={{ width: 24, height: 24, fontSize: 14 }}
                >
                  ↓
                </IconButton>
              </Box>
            ))}
          </Box>
        </Paper>
      ))}

      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 2 }}>
        <Button
          variant="contained"
          onClick={() => save(tiers)}
          disabled={saving || !unsaved}
        >
          Save
        </Button>
        <Button
          onClick={() => order !== null && save(order.default_tiers)}
          disabled={saving || order === null}
        >
          Reset
        </Button>
        {unsaved && <Typography>Not saved yet.</Typography>}
      </Box>
    </Box>
  );
}
