from pydantic import BaseModel


class TrackRead(BaseModel):
    id: int
    file_path: str
    artist: str | None = None
    album: str | None = None
    title: str | None = None
    track_number: int | None = None
    year: int | None = None
    format: str | None = None
    bit_rate: int | None = None
    sample_rate: int | None = None
    duration: float | None = None
    collection_id: int

    class Config:
        from_attributes = True