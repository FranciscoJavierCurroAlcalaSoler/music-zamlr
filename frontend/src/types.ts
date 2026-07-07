export interface Track {
  id: number;
  file_path: string;
  artist: string | null;
  album: string | null;
  title: string | null;
  track_number: number | null;
  year: number | null;
  format: string | null;
  bit_rate: number | null;
  sample_rate: number | null;
  duration: number | null;
}