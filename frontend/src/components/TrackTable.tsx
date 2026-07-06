import { useEffect, useState } from 'react';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { Box } from '@mui/material';
import type { Track } from '../types';

const columns: GridColDef[] = [
  { field: 'title', headerName: 'Title', flex: 1 },
  { field: 'artist', headerName: 'Artist', flex: 1 },
  { field: 'album', headerName: 'Album', flex: 1 },
  { field: 'format', headerName: 'Format', width: 90 },
  { field: 'bit_rate', headerName: 'Bitrate', width: 100 },
];

export function TrackTable() {
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8000/api/tracks')
      .then((res) => res.json())
      .then(setTracks)
      .finally(() => setLoading(false));
  }, []);

  return (
    <Box sx={{ height: 600, width: '100%' }}>
      <DataGrid rows={tracks} columns={columns} loading={loading} />
    </Box>
  );
}