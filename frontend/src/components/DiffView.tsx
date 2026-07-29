import { useEffect, useState, useMemo } from 'react';
import { Alert, Box, Select, MenuItem, InputLabel, Stack, FormControl, Button, ToggleButton, ToggleButtonGroup, Tabs, Tab, Typography } from "@mui/material";
import { DataGrid } from '@mui/x-data-grid';
import type { GridColDef, GridRowSelectionModel, GridRowParams } from "@mui/x-data-grid";
import type { Track, Match, Collection, Diff } from '../types';
import { ImportSettings } from './ImportSettings';

type BucketKey = 'missing' | 'upgrade_available' | 'already_have' | 'needs_review';

interface DiffRow {
  id: number;
  bucket: BucketKey;
  title: string | null;
  artist: string | null;
  album: string | null;
  format: string | null;
  bit_rate: number | null;
  duration: number | null;
  mine_format: string | null;    // null for single-track buckets
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

const columns: GridColDef[] = [
  { field: 'bucket', headerName: 'Status', width: 140 },
  { field: 'title', headerName: 'Title', flex: 1 },
  { field: 'artist', headerName: 'Artist', flex: 1 },
  { field: 'album', headerName: 'Album', flex: 1 },
  { field: 'format', headerName: 'Format', width: 90 },
  { field: 'bit_rate', headerName: 'Bitrate', width: 100 },
  { field: 'duration', headerName: 'Duration', width: 100 },
  { field: 'mine_format', headerName: 'Your format', width: 110 },
  { field: 'mine_bit_rate', headerName: 'Your bitrate', width: 110 },
];

const onlyInMineColumns: GridColDef[] = [
  { field: 'title', headerName: 'Title', flex: 1 },
  { field: 'artist', headerName: 'Artist', flex: 1 },
  { field: 'album', headerName: 'Album', flex: 1 },
  { field: 'format', headerName: 'Format', width: 90 },
  { field: 'bit_rate', headerName: 'Bitrate', width: 100 },
  { field: 'duration', headerName: 'Duration', width: 100 },
];

export function DiffView() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loadingCollections, setLoadingCollections] = useState(true);
  const [loadingDiff, setLoadingDiff] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mineId, setMineId] = useState<number | "">("");
  const [theirsId, setTheirsId] = useState<number | "">("");
  const [diff, setDiff] = useState<Diff | null>(null);
  const [bucket, setBucket] = useState<BucketKey | 'all'>('all');
  const [tab, setTab] = useState(0);
  const [selection, setSelection] = useState<GridRowSelectionModel>({
    type: "include",
    ids: new Set(),
  });

  useEffect(() => {
    let cancelled = false;

    fetch('http://localhost:8000/api/collections')
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Server responded with ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        if (!cancelled) setCollections(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoadingCollections(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const rows: DiffRow[] = useMemo(() => {
    if (!diff) return [];
    const r = diff.match_results;

    const fromTrack = (t: Track, bucketKey: BucketKey): DiffRow => ({
        id: t.id,
        bucket: bucketKey,
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

    return [
        ...r.missing.map((t) => fromTrack(t, 'missing')),
        ...r.needs_review.map((t) => fromTrack(t, 'needs_review')),
        ...r.upgrade_available.map((m) => fromMatch(m, 'upgrade_available')),
        ...r.already_have.map((m) => fromMatch(m, 'already_have')),
    ];
    }, [diff]);

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

  const visibleRows = bucket === 'all' ? rows : rows.filter((r) => r.bucket === bucket);

  async function runDiff() {
    setLoadingDiff(true);
    setError(null);
    setSelection({ type: "include", ids: new Set() });
    try {
        const res = await fetch(`http://localhost:8000/api/diff?mine=${mineId}&theirs=${theirsId}`);
        if (!res.ok) {
        const body = await res.json();
        setError(body.detail ?? "Diff failed");
        return;
        }
        const data: Diff = await res.json();
        setDiff(data);
    } catch {
        setError("Could not reach the server");
    } finally {
        setLoadingDiff(false);
    }
  }

  return (
    <Box>
      {error && <Alert severity="error">Error: {error}</Alert>}
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
              <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>
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
              <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>
      <Button
        variant="contained"
        disabled={loadingCollections || loadingDiff || mineId === "" || mineId === 0 || theirsId === "" || theirsId === 0 || mineId === theirsId}
        onClick={runDiff}
      >
        {loadingDiff ? "Comparing…" : "Compare"}
      </Button>
      {diff && (
        <Box sx={{ height: 600, width: '100%', display: 'flex', flexDirection: 'column' }}>
          <Tabs value={tab} onChange={(_, next) => setTab(next)}>
            <Tab label={`Import candidates (${rows.length})`} />
            <Tab label={`Only in mine (${diff.match_counts.only_in_mine})`} />
          </Tabs>

          {tab === 0 && (
            <>
              <ToggleButtonGroup
                value={bucket}
                exclusive
                onChange={(_, next) => { if (next !== null) setBucket(next); }}
                size="small"
              >
                <ToggleButton value="all">All ({rows.length})</ToggleButton>
                <ToggleButton value="missing">Missing ({diff.match_counts.missing})</ToggleButton>
                <ToggleButton value="upgrade_available">Upgrades ({diff.match_counts.upgrade_available})</ToggleButton>
                <ToggleButton value="already_have">Already have ({diff.match_counts.already_have})</ToggleButton>
                <ToggleButton value="needs_review">Needs review ({diff.match_counts.needs_review})</ToggleButton>
              </ToggleButtonGroup>
              <Typography variant="body2">{selection.ids.size} selected</Typography>
              <DataGrid
                rows={visibleRows}
                columns={columns}
                loading={loadingDiff}
                checkboxSelection
                disableRowSelectionExcludeModel
                keepNonExistentRowsSelected
                rowSelectionModel={selection}
                onRowSelectionModelChange={setSelection}
                isRowSelectable={(params: GridRowParams) =>
                  params.row.bucket === 'missing' || params.row.bucket === 'upgrade_available'
                }
                sx={{ flex: 1, minHeight: 0 }}
              />
              <ImportSettings
                disabled={selection.ids.size === 0}
                onPreview={(settings) => {
                  console.log('settings', settings);
                  console.log('track ids', [...selection.ids]);
                }}
              />
            </>
          )}

          {tab === 1 && (
            <DataGrid rows={onlyInMineRows} columns={onlyInMineColumns} loading={loadingDiff} sx={{ flex: 1, minHeight: 0 }} />
          )}
        </Box>
      )}
    </Box>);
}