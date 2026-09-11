import { useState, useMemo, useCallback } from "react";
import {
  Alert,
  Box,
  Select,
  MenuItem,
  InputLabel,
  Stack,
  FormControl,
  Button,
  ToggleButton,
  ToggleButtonGroup,
  Tabs,
  Tab,
  Typography,
} from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import type {
  GridColDef,
  GridRowSelectionModel,
  GridRowParams,
  GridRenderCellParams,
} from "@mui/x-data-grid";
import type {
  Track,
  Match,
  Collection,
  DiffResult,
  DiffProgress,
  ImportPreview,
  ImportSettingsValues,
  ImportResult,
  AmbiguousMatch,
  ImportProgress,
} from "../types";
import {
  fetchDiff,
  previewImport,
  executeImport,
  describeFetchError,
} from "../api";
import { ImportSettings } from "./ImportSettings";
import { ImportPreviewDialog } from "./ImportPreviewDialog";
import { ImportProgressView } from "./ImportProgressView";
import { ImportResultView } from "./ImportResultView";
import { ResolveMatchDialog } from "./ResolveMatchDialog";
import { DiffProgressView } from "./DiffProgressView";
import { bitrate, duration, formatCount } from "../format";

type BucketKey =
  "missing" | "upgrade_available" | "already_have" | "needs_review";

interface DiffRow {
  id: number;
  bucket: BucketKey;
  resolvedTo: number | null | undefined;
  // Set only on missing rows the fingerprint tier refused. A plain missing
  // row and a rejected one are otherwise identical on screen, and the user
  // then imports the duplicate the tier exists to prevent.
  rejected: boolean;
  title: string | null;
  artist: string | null;
  album: string | null;
  format: string | null;
  bit_rate: number | null;
  duration: number | null;
  mine_format: string | null; // null for single-track buckets
  mine_bit_rate: number | null;
}

interface OnlyInMineRow {
  id: number;
  title: string | null;
  artist: string | null;
  album: string | null;
  format: string | null;
  bit_rate: number | null;
  duration: number | null;
}

const diffColumns: GridColDef[] = [
  {
    field: "bucket",
    headerName: "Status",
    width: 200,
    valueGetter: (_value, row: DiffRow) =>
      describeStatus(row.bucket, row.resolvedTo, row.rejected),
  },
  { field: "title", headerName: "Title", flex: 1 },
  { field: "artist", headerName: "Artist", flex: 1 },
  { field: "album", headerName: "Album", flex: 1 },
  { field: "format", headerName: "Format", width: 90 },
  // Raw without these: a bitrate reads as 1411200 and a duration as 614.
  // valueFormatter rather than renderCell, so sorting and filtering still use
  // the underlying number — the same reason the Status column uses valueGetter.
  {
    field: "bit_rate",
    headerName: "Bitrate",
    width: 100,
    valueFormatter: (value: number | null) => bitrate(value),
  },
  {
    field: "duration",
    headerName: "Duration",
    width: 100,
    valueFormatter: (value: number | null) => duration(value),
  },
  { field: "mine_format", headerName: "Your format", width: 110 },
  {
    field: "mine_bit_rate",
    headerName: "Your bitrate",
    width: 110,
    valueFormatter: (value: number | null) => bitrate(value),
  },
];

const onlyInMineColumns: GridColDef[] = [
  { field: "title", headerName: "Title", flex: 1 },
  { field: "artist", headerName: "Artist", flex: 1 },
  { field: "album", headerName: "Album", flex: 1 },
  { field: "format", headerName: "Format", width: 90 },
  {
    field: "bit_rate",
    headerName: "Bitrate",
    width: 100,
    valueFormatter: (value: number | null) => bitrate(value),
  },
  {
    field: "duration",
    headerName: "Duration",
    width: 100,
    valueFormatter: (value: number | null) => duration(value),
  },
];

interface DiffViewProps {
  collections: Collection[];
  loadingCollections: boolean;
}

function describeStatus(
  bucket: BucketKey,
  resolvedTo: number | null | undefined,
  rejected: boolean,
): string {
  // The rejection wording is short because the evidence is already on the
  // row: "Your format" and "Your bitrate" carry the file it was compared
  // against, so the label only has to say why the pairing was refused.
  //
  // No error rate. 0.27 means nothing to a reader, and a number invites the
  // belief that a smaller one would have been accepted.
  if (bucket === "missing") {
    return rejected ? "Missing · audio differs" : "Missing";
  }
  if (bucket === "upgrade_available") return "Upgrade";
  if (bucket === "already_have") return "Already have";
  // Checked, not asserted in a comment: a fifth bucket would break the build
  // here rather than quietly falling through to the "replaces yours" label.
  bucket satisfies "needs_review";
  if (resolvedTo === undefined) return "Needs review";
  if (resolvedTo === null) return "Resolved · import as new";
  /* From here on, resolvedTo can only be a number. */
  return "Resolved · replaces yours";
}

export function DiffView({ collections, loadingCollections }: DiffViewProps) {
  const [loadingDiff, setLoadingDiff] = useState(false);
  const [progress, setProgress] = useState<DiffProgress | null>(null);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [mineId, setMineId] = useState<number | "">("");
  const [theirsId, setTheirsId] = useState<number | "">("");
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [bucket, setBucket] = useState<BucketKey | "all">("all");
  const [tab, setTab] = useState(0);
  const [selection, setSelection] = useState<GridRowSelectionModel>({
    type: "include",
    ids: new Set(),
  });
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewProgress, setPreviewProgress] = useState<ImportProgress | null>(
    null,
  );
  const [lastSettings, setLastSettings] = useState<ImportSettingsValues | null>(
    null,
  );
  const [result, setResult] = useState<ImportResult | null>(null);
  const [executing, setExecuting] = useState(false);
  const [executeProgress, setExecuteProgress] = useState<ImportProgress | null>(
    null,
  );
  const [diffScannedAt, setDiffScannedAt] = useState<{
    mine: string | null;
    theirs: string | null;
  } | null>(null);
  const [reviewing, setReviewing] = useState<AmbiguousMatch | null>(null);
  const [resolutions, setResolutions] = useState<Map<number, number | null>>(
    new Map(),
  );

  const rows: DiffRow[] = useMemo(() => {
    if (!diff) return [];
    const r = diff.match_results;

    // Keyed by the track of theirs, because that is the row being built. The
    // value is my file, not the rate: the columns show what I have, and the
    // number stays off screen.
    const rejectedAgainst = new Map(
      r.rejected.map((x) => [x.theirs.id, x.mine]),
    );

    const fromTrack = (
      t: Track,
      bucketKey: BucketKey,
      resolvedTo?: number | null,
    ): DiffRow => ({
      id: t.id,
      bucket: bucketKey,
      resolvedTo,
      rejected: false,
      title: t.title,
      artist: t.artist,
      album: t.album,
      format: t.format,
      bit_rate: t.bit_rate,
      duration: t.duration,
      mine_format: null,
      mine_bit_rate: null,
    });

    const fromMatch = (m: Match, bucketKey: BucketKey): DiffRow => ({
      ...fromTrack(m.theirs, bucketKey),
      mine_format: m.mine.format,
      mine_bit_rate: m.mine.bit_rate,
    });

    // A rejected track is a missing track that also knows what it was
    // compared against, so it fills the two "yours" columns the same way a
    // Match does. No new column, and the evidence sits beside the label.
    const fromMissing = (t: Track): DiffRow => {
      const mine = rejectedAgainst.get(t.id);
      if (mine === undefined) return fromTrack(t, "missing");
      return {
        ...fromTrack(t, "missing"),
        rejected: true,
        mine_format: mine.format,
        mine_bit_rate: mine.bit_rate,
      };
    };

    return [
      ...r.missing.map(fromMissing),
      ...r.needs_review.map((a) =>
        fromTrack(a.theirs, "needs_review", resolutions.get(a.theirs.id)),
      ),
      ...r.upgrade_available.map((m) => fromMatch(m, "upgrade_available")),
      ...r.already_have.map((m) => fromMatch(m, "already_have")),
    ];
  }, [diff, resolutions]);

  const onlyInMineRows: OnlyInMineRow[] = useMemo(() => {
    if (!diff) return [];

    return diff.match_results.only_in_mine.map((t) => ({
      id: t.id,
      title: t.title,
      artist: t.artist,
      album: t.album,
      format: t.format,
      bit_rate: t.bit_rate,
      duration: t.duration,
    }));
  }, [diff]);

  const ambiguityByTheirsId = useMemo(() => {
    if (!diff) return new Map<number, AmbiguousMatch>();

    return new Map<number, AmbiguousMatch>(
      diff.match_results.needs_review.map((ambiguity) => [
        ambiguity.theirs.id,
        ambiguity,
      ]),
    );
  }, [diff]);

  const claimedElsewhere = useMemo(() => {
    const claims = new Map<number, string>();
    resolutions.forEach((mineTrackId, theirsTrackId) => {
      if (mineTrackId === null) return;
      if (theirsTrackId === reviewing?.theirs.id) return;
      if (!selection.ids.has(theirsTrackId)) return;
      claims.set(
        mineTrackId,
        ambiguityByTheirsId.get(theirsTrackId)?.theirs.file_name ??
          "another track",
      );
    });
    return claims;
  }, [selection, resolutions, reviewing, ambiguityByTheirsId]);

  const openReview = useCallback(
    (trackId: number) => {
      const ambiguity = ambiguityByTheirsId.get(trackId);
      if (ambiguity !== undefined) {
        setReviewing(ambiguity);
      }
    },
    [ambiguityByTheirsId],
  );

  const columns = useMemo<GridColDef[]>(
    () => [
      ...diffColumns,
      {
        field: "review",
        headerName: "Review",
        width: 110,
        sortable: false,
        filterable: false,
        disableColumnMenu: true,
        renderCell: (params: GridRenderCellParams) =>
          params.row.bucket === "needs_review" ? (
            <Button
              onClick={(e) => {
                e.stopPropagation();
                openReview(params.row.id);
              }}
            >
              {params.row.resolvedTo !== undefined ? "Change" : "Review"}
            </Button>
          ) : null,
      },
    ],
    [openReview],
  );

  const scannedAt = (id: number | "") =>
    collections.find((c) => c.id === id)?.last_scanned_at ?? null;

  const visibleRows =
    bucket === "all" ? rows : rows.filter((r) => r.bucket === bucket);

  const stale =
    diff !== null &&
    diffScannedAt !== null &&
    (scannedAt(mineId) !== diffScannedAt.mine ||
      scannedAt(theirsId) !== diffScannedAt.theirs);

  async function runDiff() {
    setLoadingDiff(true);
    setDiffError(null);
    setSelection({ type: "include", ids: new Set() });
    setPreview(null);
    setLastSettings(null);
    setResolutions(new Map());
    try {
      if (mineId === "" || theirsId === "") {
        throw new Error("Select both collections first.");
      }
      const result: DiffResult = await fetchDiff(mineId, theirsId, setProgress);
      setDiff(result);
      setDiffScannedAt({
        mine: scannedAt(mineId),
        theirs: scannedAt(theirsId),
      });
    } catch (error: unknown) {
      setDiffError(describeFetchError(error));
    } finally {
      setLoadingDiff(false);
      setProgress(null);
    }
  }

  function resolveReviewing(mineId: number | null) {
    if (reviewing === null) return;
    const theirsTrackId = reviewing.theirs.id;
    setResolutions((resolutions) => {
      const newResolutions = new Map(resolutions);
      newResolutions.set(theirsTrackId, mineId);
      return newResolutions;
    });
    setSelection((previous) => ({
      ...previous,
      ids: new Set(previous.ids).add(theirsTrackId),
    }));
    setReviewing(null);
  }

  function importRequestBody(settings: ImportSettingsValues) {
    if (mineId === "" || theirsId === "") {
      throw new Error("Select both collections first.");
    }
    return {
      // DataGrid types row ids as string | number in general; ours are Track.id,
      // which is always a number.
      track_ids: [...selection.ids].map(Number),
      mine_collection_id: mineId,
      theirs_collection_id: theirsId,
      destination_root: settings.destinationRoot,
      structure_mode: settings.structureMode,
      upgrade_action: settings.upgradeAction,
      resolutions: [...resolutions].map(([theirsTrackId, mineTrackId]) => ({
        theirs_id: theirsTrackId,
        mine_id: mineTrackId,
      })),
    };
  }

  async function runPreview(settings: ImportSettingsValues) {
    setLastSettings(settings);
    setPreviewing(true);
    setImportError(null);
    try {
      const result = await previewImport(
        importRequestBody(settings),
        setPreviewProgress,
      );
      setPreview(result);
    } catch (error: unknown) {
      setImportError(describeFetchError(error));
    } finally {
      setPreviewing(false);
      setPreviewProgress(null);
    }
  }

  async function runExecute() {
    if (lastSettings === null) return;

    setExecuting(true);
    setImportError(null);
    try {
      const result = await executeImport(
        importRequestBody(lastSettings),
        setExecuteProgress,
      );
      setPreview(null);
      setResult(result);
      setDiff(null);
      setSelection({ type: "include", ids: new Set() });
    } catch (error: unknown) {
      setImportError(describeFetchError(error));
    } finally {
      setExecuting(false);
      setExecuteProgress(null);
    }
  }

  return (
    <>
      <Box>
        {diffError && <Alert severity="error">Error: {diffError}</Alert>}
        <Stack direction="row" spacing={2}>
          <FormControl fullWidth>
            <InputLabel id="mine-label">My collection</InputLabel>
            <Select
              labelId="mine-label"
              value={mineId}
              label="My collection"
              onChange={(e) => setMineId(Number(e.target.value))}
            >
              {collections.map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl fullWidth>
            <InputLabel id="theirs-label">Their collection</InputLabel>
            <Select
              labelId="theirs-label"
              value={theirsId}
              label="Their collection"
              onChange={(e) => setTheirsId(Number(e.target.value))}
            >
              {collections.map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
        <Button
          variant="contained"
          disabled={
            loadingCollections ||
            loadingDiff ||
            mineId === "" ||
            mineId === 0 ||
            theirsId === "" ||
            theirsId === 0 ||
            mineId === theirsId
          }
          onClick={runDiff}
        >
          {loadingDiff ? "Comparing…" : "Compare"}
        </Button>
        <DiffProgressView progress={progress} />
        {diff && (
          <>
            <Box
              sx={{
                height: 600,
                width: "100%",
                display: "flex",
                flexDirection: "column",
              }}
            >
              {stale && (
                <Alert severity="info" sx={{ mt: 1 }}>
                  These collections were re-scanned since this comparison. Run
                  Compare again for current results.
                </Alert>
              )}
              {/* The text names the risk, not only the fault. Without the
                  audio, the upgrade bucket is the dangerous one: with the
                  delete action, a different recording of the song replaces
                  the user's file. */}
              {diff.match_results.fingerprints_available === false && (
                <Alert severity="warning" sx={{ mt: 1 }}>
                  fpcalc was not found, so this comparison did not check the
                  audio. Tracks were matched by their tags only, and an upgrade
                  can be a different recording of the song. The README says how
                  to install fpcalc.
                </Alert>
              )}
              <Tabs value={tab} onChange={(_, next) => setTab(next)}>
                <Tab
                  label={`Import candidates (${formatCount(rows.length)})`}
                />
                <Tab
                  label={`Only in mine (${formatCount(diff.match_counts.only_in_mine)})`}
                />
              </Tabs>

              {tab === 0 && (
                <>
                  <ToggleButtonGroup
                    value={bucket}
                    exclusive
                    onChange={(_, next) => {
                      if (next !== null) setBucket(next);
                    }}
                    size="small"
                  >
                    <ToggleButton value="all">
                      All ({formatCount(rows.length)})
                    </ToggleButton>
                    <ToggleButton value="missing">
                      Missing ({formatCount(diff.match_counts.missing)})
                    </ToggleButton>
                    <ToggleButton value="upgrade_available">
                      Upgrades (
                      {formatCount(diff.match_counts.upgrade_available)})
                    </ToggleButton>
                    <ToggleButton value="already_have">
                      Already have (
                      {formatCount(diff.match_counts.already_have)})
                    </ToggleButton>
                    <ToggleButton value="needs_review">
                      Needs review (
                      {formatCount(diff.match_counts.needs_review)})
                    </ToggleButton>
                  </ToggleButtonGroup>
                  <Typography variant="body2">
                    {formatCount(selection.ids.size)} selected
                  </Typography>
                  {/* No loading prop, deliberately. DataGrid draws its own
                      indeterminate bar under the header, and DiffProgressView
                      above already shows a determinate one with counts and the
                      current file. Two bars for one operation read as two
                      operations. This grid only exists once a diff has been
                      computed, so its bar could never appear except during a
                      re-run, which is exactly when the other one is there. */}
                  <DataGrid
                    rows={visibleRows}
                    columns={columns}
                    checkboxSelection
                    disableRowSelectionExcludeModel
                    keepNonExistentRowsSelected
                    rowSelectionModel={selection}
                    onRowSelectionModelChange={setSelection}
                    isRowSelectable={(params: GridRowParams) =>
                      params.row.bucket === "missing" ||
                      params.row.bucket === "upgrade_available" ||
                      (params.row.bucket === "needs_review" &&
                        params.row.resolvedTo !== undefined)
                    }
                    sx={{ flex: 1, minHeight: 0 }}
                  />
                </>
              )}

              {tab === 1 && (
                <DataGrid
                  rows={onlyInMineRows}
                  columns={onlyInMineColumns}
                  sx={{ flex: 1, minHeight: 0 }}
                />
              )}
            </Box>
            <ImportSettings
              disabled={selection.ids.size === 0 || stale}
              loading={previewing}
              error={importError}
              onPreview={runPreview}
            />
            {/* The preview's progress only. The import's lives inside
                ImportPreviewDialog, because that dialog stays open and
                unclosable for the whole run, so anything here would sit
                behind its backdrop. */}
            <ImportProgressView progress={previewProgress} />
          </>
        )}
        <ImportResultView result={result} onDismiss={() => setResult(null)} />
      </Box>
      <ImportPreviewDialog
        preview={preview}
        destinationRoot={lastSettings?.destinationRoot ?? ""}
        executing={executing}
        executeProgress={executeProgress}
        onCancel={() => setPreview(null)}
        onConfirm={runExecute}
      />
      <ResolveMatchDialog
        key={reviewing?.theirs.id}
        ambiguity={reviewing}
        chosenMineId={
          reviewing ? resolutions?.get(reviewing.theirs.id) : undefined
        }
        claimedElsewhere={claimedElsewhere}
        onResolve={resolveReviewing}
        onCancel={() => setReviewing(null)}
      />
    </>
  );
}
