from sqlmodel import SQLModel, Field

class Track (SQLModel, table=True):
  id: int | None = Field(default=None, primary_key=True)
  file_path: str = Field(unique=True, index=True)
  file_name: str
  title: str | None = None
  artist: str | None = None
  album: str | None = None
  track_number: int | None = None
  year: int | None = None
  format: str | None = None
  bit_depth: int | None = None
  bit_rate: int
  sample_rate: int
  duration: int
  file_size: int
  file_hash: str
