import { useEffect, useState } from 'react';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { Alert, Box } from '@mui/material';
import type { Track } from '../types';

const columns: GridColDef[] = [
  { field: 'title', headerName: 'Title', flex: 1 },
  { field: 'artist', headerName: 'Artist', flex: 1 },
  { field: 'album', headerName: 'Album', flex: 1 },
  { field: 'format', headerName: 'Format', width: 90 },
  { field: 'bitrate', headerName: 'Bitrate', width: 100 },
];

export function TrackTable() {
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetch('http://localhost:8000/api/tracks')
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Server responded with ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        if (!cancelled) setTracks(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return <Alert severity="error">Couldn't load tracks: {error}</Alert>;
  }

  return (
    <Box sx={{ height: 600, width: '100%' }}>
      <DataGrid rows={tracks} columns={columns} loading={loading} />
    </Box>
  );
}